"""Grid-search DBSCAN (min_samples x epsilon x shape_weight) on citizen-science points,
score each combination against the expert points, and write every result to a CSV.

Per image: DBSCAN with d(a,b) = sqrt((w*dx)^2 + ((2-w)*dy)^2); centroid = mean of each
cluster's points (noise label -1 excluded); greedy match centroids to expert points by
STANDARD Euclidean distance, closest pairs first, each point used once, distance <= max.
F1 = 2PR/(P+R) with P = matches/clusters, R = matches/expert points; delta = mean
matched Euclidean distance. No points / no clusters / no matches -> F1 0.0, delta NaN.
Averages run over every expert image: F1 includes the zeros, delta skips NaN.

Speed (the client kills scripts after ~60 s): the metric matrix is built and row-sorted
once per (image, w); labels come from sklearn's own DBSCAN core loop (dbscan_inner) once
per distinct core set, which reproduces DBSCAN(eps, min_samples, metric="precomputed")
exactly; scores are cached per distinct labelling of an image across the whole grid.
If that private sklearn helper is unavailable, an equivalent connected-components
labelling (same seeding order, so same border-point assignment) is used.

Checkpointing: each finished image chunk is saved under <work_dir>/chunks/, keyed by the
grid, the chunk's image keys and the input files' size/mtime. If the step is killed by a
timeout, re-running it (aip resume) reuses finished chunks and only computes the rest.
"""
import hashlib
import json
import os
import time

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy.sparse.csgraph import connected_components
from scipy.spatial.distance import cdist

try:
    from sklearn.cluster._dbscan_inner import dbscan_inner
except ImportError:  # private helper moved: fall back to the equivalent labelling below
    dbscan_inner = None

from mcc_common import emit, fail, group_points, load_config, load_points, read_payload


def shape_distance_matrix(pts, w):
    dx = pts[:, 0][:, None] - pts[:, 0][None, :]
    dy = pts[:, 1][:, None] - pts[:, 1][None, :]
    return np.sqrt((w * dx) ** 2 + ((2 - w) * dy) ** 2)


def dbscan_labels(adj, neighborhoods, core):
    """Labels identical to sklearn DBSCAN(eps, min_samples, metric='precomputed') where
    adj = D <= eps, neighborhoods[i] = indices adjacent to i, core = (#neighbours >= min_samples)."""
    labels = np.full(len(core), -1, dtype=np.intp)
    if dbscan_inner is not None:
        dbscan_inner(core.astype(np.uint8), neighborhoods, labels)
        return labels
    ci = np.flatnonzero(core)
    nc, comp = connected_components(adj[np.ix_(ci, ci)], directed=False)
    first = np.full(nc, len(core))
    np.minimum.at(first, comp, ci)  # clusters are seeded in order of their lowest core index
    rank = np.empty(nc, dtype=np.intp)
    rank[np.argsort(first)] = np.arange(nc)
    labels[ci] = rank[comp]
    nonc = np.flatnonzero(~core)
    if nonc.size:  # a border point joins the earliest-seeded cluster that reaches it
        r = np.where(adj[np.ix_(nonc, ci)], rank[comp][None, :], nc).min(axis=1)
        labels[nonc[r < nc]] = r[r < nc]
    return labels


def greedy_match(centroids, experts, max_dist):
    """Greedy one-to-one matching on STANDARD Euclidean distance (not the shape-weighted
    metric): closest pairs first, each centroid and expert point used once, distance <= max."""
    d = cdist(centroids, experts)
    n_exp = d.shape[1]
    flat = d.ravel()
    order = np.argsort(flat, kind="stable")
    ranked = flat[order]
    cut = int(np.searchsorted(ranked, max_dist, side="right"))
    used_c, used_e, matched = set(), set(), []
    for idx, dist in zip(order[:cut].tolist(), ranked[:cut].tolist()):
        i, j = divmod(idx, n_exp)
        if i in used_c or j in used_e:
            continue
        used_c.add(i)
        used_e.add(j)
        matched.append(dist)
    return matched


def score_image(labels, pts, experts, max_dist):
    keep = labels >= 0
    if not keep.any():
        return 0.0, np.nan
    lab = labels[keep]
    n = int(lab.max()) + 1  # DBSCAN labels are 0..n-1 with no gaps
    cnt = np.bincount(lab, minlength=n)
    centroids = np.column_stack([np.bincount(lab, pts[keep, 0], n) / cnt,
                                 np.bincount(lab, pts[keep, 1], n) / cnt])
    matched = greedy_match(centroids, experts, max_dist)
    if not matched:
        return 0.0, np.nan
    tp = len(matched)
    p, r = tp / n, tp / len(experts)
    return 2 * p * r / (p + r), sum(matched) / tp


def evaluate_images(images, min_samples, epsilons, weights, max_dist):
    """F1 and delta for every (min_samples, epsilon, shape_weight) on a chunk of images,
    shaped (len(min_samples), len(epsilons), len(weights), len(images)).
    Images without citizen-science points keep F1 0.0 and delta NaN."""
    shape = (len(min_samples), len(epsilons), len(weights), len(images))
    f1 = np.zeros(shape)
    delta = np.full(shape, np.nan)
    for k, (experts, pts) in enumerate(images):
        if pts is None or len(pts) == 0:
            continue
        n = len(pts)
        cache = {}  # distinct labelling -> (F1, delta), shared across the whole grid for this image
        for c, w in enumerate(weights):
            D = shape_distance_matrix(pts, w)
            order = np.argsort(D, axis=1, kind="stable")
            sorted_d = np.take_along_axis(D, order, axis=1)
            prev_counts = None
            for b, eps in enumerate(epsilons):  # ascending, so neighbourhoods only grow
                counts = (sorted_d <= eps).sum(axis=1)  # neighbours within eps, self included
                if prev_counts is not None and np.array_equal(counts, prev_counts):
                    f1[:, b, c, k], delta[:, b, c, k] = f1[:, b - 1, c, k], delta[:, b - 1, c, k]
                    continue  # same counts with a larger eps means the same adjacency
                prev_counts = counts
                adj = neighborhoods = prev_core = prev_score = None
                for a, ms in enumerate(min_samples):
                    core = counts >= ms
                    if not core.any():
                        continue  # no core points -> no clusters -> F1 0, delta NaN
                    if prev_core is None or not np.array_equal(core, prev_core):
                        if neighborhoods is None:
                            adj = D <= eps
                            neighborhoods = np.empty(n, dtype=object)
                            neighborhoods[:] = [order[i, :counts[i]] for i in range(n)]
                        labels = dbscan_labels(adj, neighborhoods, core)
                        key = labels.tobytes()
                        if key not in cache:
                            cache[key] = score_image(labels, pts, experts, max_dist)
                        prev_core, prev_score = core, cache[key]
                    f1[a, b, c, k], delta[a, b, c, k] = prev_score
    return f1, delta


def run_chunk(path, images, ms_list, eps_list, w_list, max_dist):
    if os.path.isfile(path):
        with np.load(path) as z:
            return z["f1"], z["delta"]
    f1, delta = evaluate_images(images, ms_list, eps_list, w_list, max_dist)
    tmp = path + ".tmp.npz"
    np.savez(tmp, f1=f1, delta=delta)
    os.replace(tmp, path)  # atomic: a killed worker never leaves a half-written checkpoint
    return f1, delta


def main():
    t0 = time.time()
    state, assets = read_payload()
    cfg = load_config(assets)
    space = state["resolved_search_space"]
    work_dir = state["work_dir"]
    os.makedirs(work_dir, exist_ok=True)
    ms_list = [int(v) for v in space["min_samples"]]
    eps_list = sorted(space["epsilon"])
    w_list = [round(float(v), cfg["shape_weight_decimals"]) for v in space["shape_weight"]]

    cit, _, _ = load_points(state["citsci_csv"], cfg, "citizen-science")
    exp, _, _ = load_points(state["expert_csv"], cfg, "expert")
    cit_imgs, exp_imgs = group_points(cit, cfg), group_points(exp, cfg)
    if not exp_imgs:
        fail("no expert images to evaluate")
    # Loop over every expert image, including those without citizen-science points.
    images = [(exp_imgs[k], cit_imgs.get(k)) for k in exp_imgs]

    # Balance chunks by work (~ points^2) and give each worker several chunks.
    n_jobs = max(1, min(os.cpu_count() or 1, len(images)))
    n_chunks = min(len(images), max(24, n_jobs * 4))
    cost = [len(p) ** 2 if p is not None else 0 for _, p in images]
    chunks, loads = [[] for _ in range(n_chunks)], [0] * n_chunks
    for i in sorted(range(len(images)), key=lambda i: -cost[i]):
        j = loads.index(min(loads))
        chunks[j].append(i)
        loads[j] += cost[i]
    chunks = [sorted(c) for c in chunks if c]

    keys = list(exp_imgs)
    stamp = [[os.path.getsize(p), os.path.getmtime(p)] for p in (state["citsci_csv"], state["expert_csv"])]
    ckpt_dir = os.path.join(work_dir, "chunks")
    os.makedirs(ckpt_dir, exist_ok=True)

    def ckpt(c):
        blob = json.dumps([ms_list, eps_list, w_list, cfg["max_match_distance"], stamp, [keys[i] for i in c]])
        return os.path.join(ckpt_dir, hashlib.sha1(blob.encode()).hexdigest() + ".npz")

    reused = sum(os.path.isfile(ckpt(c)) for c in chunks)
    # backend="multiprocessing": joblib 1.3.2 loky workers spam ResourceTracker errors at exit on Python 3.12
    parts = Parallel(n_jobs=n_jobs, backend="multiprocessing")(
        delayed(run_chunk)(ckpt(c), [images[i] for i in c], ms_list, eps_list, w_list, float(cfg["max_match_distance"]))
        for c in chunks
    )
    shape = (len(ms_list), len(eps_list), len(w_list), len(images))
    f1, delta = np.zeros(shape), np.full(shape, np.nan)
    for c, (pf, pd_) in zip(chunks, parts):
        f1[..., c], delta[..., c] = pf, pd_

    rows = []
    for a, ms in enumerate(ms_list):
        for b, eps in enumerate(eps_list):
            for c, w in enumerate(w_list):
                d = delta[a, b, c]
                n_matched = int(np.count_nonzero(~np.isnan(d)))
                rows.append({
                    "F1": float(f1[a, b, c].mean()),  # all expert images, zeros included
                    "delta": float(np.nanmean(d)) if n_matched else np.nan,  # matched images only
                    "min_samples": ms, "epsilon": eps, "shape_weight": w,
                    "images_with_matches": n_matched,
                })
    res = pd.DataFrame(rows)
    out = os.path.join(work_dir, "grid_results.csv")
    res.to_csv(out, index=False)  # full repr precision so rounding and ties are decided on exact values

    passing = res[res["F1"] > cfg["min_f1"]]
    best = res.loc[res["F1"].idxmax()]
    summary = {
        "n_combinations": int(len(res)), "n_images": len(images), "n_jobs": n_jobs,
        "chunks": len(chunks), "chunks_reused_from_checkpoint": int(reused),
        "n_passing_min_f1": int(len(passing)), "min_f1": cfg["min_f1"],
        "best_f1": round(float(best["F1"]), 5),
        "best_f1_params": {"min_samples": int(best["min_samples"]), "epsilon": best["epsilon"].item(),
                           "shape_weight": float(best["shape_weight"])},
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    emit({"grid_results_csv": out, "grid_summary": summary})


if __name__ == "__main__":
    main()
