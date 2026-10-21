#!/usr/bin/env python3
"""Grid-search DBSCAN (custom shape-weighted metric) on crowd-sourced point
annotations, score each setting against expert points, and write the
F1-vs-delta Pareto frontier.

Requires: Python >= 3.9; numpy, pandas, scikit-learn, joblib, paretoset
(the Mars-clouds task container pins numpy 1.26.4, pandas 2.2.2,
scikit-learn 1.3.2, joblib 1.3.2, paretoset 1.2.3).

Per hyperparameter combo (min_samples, eps, w) and per expert image:
  1. DBSCAN on that image's citizen points with
     d(a,b) = sqrt((w*dx)^2 + ((2-w)*dy)^2)   (precomputed matrix, same formula)
  2. centroid = mean x,y (original coords) of each non-noise cluster
  3. greedy match centroids <-> expert points by plain Euclidean distance,
     closest pair first, each point used once, pair kept only if dist <= max
  4. F1 = 2PR/(P+R) with P = matches/clusters, R = matches/expert points;
     delta = mean matched Euclidean distance
     no citizen points / no clusters / no matches -> F1 = 0.0, delta = NaN
Average F1 over ALL expert images (zeros included); average delta with NaNs
skipped. Keep combos with mean F1 > threshold, then Pareto (max F1, min delta).
"""
import argparse
import itertools
import os
import sys
import time

import numpy as np
import pandas as pd


def parse_range(spec, kind):
    """'start:stop:step' (inclusive) or 'a,b,c' -> sorted list."""
    if ":" in spec:
        start, stop, step = (float(v) for v in spec.split(":"))
        n = int(round((stop - start) / step)) + 1
        vals = [start + i * step for i in range(n)]
    else:
        vals = [float(v) for v in spec.split(",") if v.strip()]
    if kind == "int":
        return [int(round(v)) for v in vals]
    return [round(v, 6) for v in vals]


def greedy_match(cents, experts, max_dist):
    """Closest-pair-first one-to-one matching; returns matched distances."""
    d = np.sqrt(((cents[:, None, :] - experts[None, :, :]) ** 2).sum(-1))
    order = np.argsort(d, axis=None, kind="stable")
    used_c, used_e, out = set(), set(), []
    for flat in order:
        i, j = divmod(int(flat), d.shape[1])
        dist = d[i, j]
        if dist > max_dist:
            break
        if i in used_c or j in used_e:
            continue
        used_c.add(i)
        used_e.add(j)
        out.append(dist)
    return out


def _dbscan_labels_factory():
    """Exact sklearn DBSCAN labels from a precomputed distance matrix.

    Fast path: sklearn's own inner loop (sklearn.cluster._dbscan_inner, the
    routine DBSCAN.fit calls) fed the same ascending-index eps-neighbourhoods
    DBSCAN(metric='precomputed') builds -> identical labels, ~30x less overhead.
    Falls back to the public DBSCAN class if the private module moves.
    """
    try:
        from sklearn.cluster._dbscan_inner import dbscan_inner
    except ImportError:  # pragma: no cover
        dbscan_inner = None
    from sklearn.cluster import DBSCAN

    def neighbourhoods(Dm, eps):
        adj = Dm <= eps
        nb = np.empty(len(Dm), dtype=object)
        nb[:] = [np.flatnonzero(r) for r in adj]
        return nb, adj.sum(axis=1)

    def labels(Dm, eps, ms, nb, cnt):
        if dbscan_inner is None:
            return DBSCAN(eps=eps, min_samples=ms, metric="precomputed").fit(Dm).labels_
        out = np.full(len(Dm), -1, dtype=np.intp)
        dbscan_inner((cnt >= ms).astype(np.uint8), nb, out)
        return out

    return neighbourhoods, labels


def eval_image(pts, experts, w_list, eps_list, ms_list, max_dist, metric):
    """Return (f1, delta) arrays indexed like the global combo list."""
    from sklearn.cluster import DBSCAN

    n_combo = len(w_list) * len(eps_list) * len(ms_list)
    f1 = np.zeros(n_combo)
    delta = np.full(n_combo, np.nan)
    if pts is None or len(pts) == 0:
        return f1, delta
    neighbourhoods, fast_labels = _dbscan_labels_factory()
    dx = pts[:, 0][:, None] - pts[:, 0][None, :]
    dy = pts[:, 1][:, None] - pts[:, 1][None, :]
    k = 0
    for w in w_list:
        Dm = np.sqrt((w * dx) ** 2 + ((2 - w) * dy) ** 2)

        def dist(a, b, w=w):
            return np.sqrt((w * (a[0] - b[0])) ** 2 + ((2 - w) * (a[1] - b[1])) ** 2)

        for eps in eps_list:
            nb, cnt = neighbourhoods(Dm, eps)
            for ms in ms_list:
                if metric == "callable":
                    labels = DBSCAN(eps=eps, min_samples=ms, metric=dist).fit(pts).labels_
                else:
                    labels = fast_labels(Dm, eps, ms, nb, cnt)
                ids = np.unique(labels[labels >= 0])
                if len(ids):
                    cents = np.array([pts[labels == c].mean(axis=0) for c in ids])
                    m = greedy_match(cents, experts, max_dist)
                    if m:
                        p, r = len(m) / len(cents), len(m) / len(experts)
                        f1[k] = 2 * p * r / (p + r)
                        delta[k] = float(np.mean(m))
                k += 1
    return f1, delta


def eval_chunk(items, *args):
    return [eval_image(pts, ex, *args) for pts, ex in items]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--citsci", default="/root/data/citsci_train.csv")
    ap.add_argument("--expert", default="/root/data/expert_train.csv")
    ap.add_argument("--out", default="/root/pareto_frontier.csv")
    ap.add_argument("--all-results", default=None, help="optional CSV of every combo (before F1 filter)")
    ap.add_argument("--image-col", default="file_rad")
    ap.add_argument("--min-samples", default="3:9:1", help="start:stop:step inclusive, or comma list")
    ap.add_argument("--eps", default="4:24:2")
    ap.add_argument("--shape-weight", default="0.9:1.9:0.1")
    ap.add_argument("--f1-threshold", type=float, default=0.5, help="keep mean F1 strictly greater")
    ap.add_argument("--max-match-dist", type=float, default=100.0)
    ap.add_argument("--keep-ties", action="store_true",
                    help="keep every combo sharing a frontier (F1, delta) value; default keeps one (paretoset distinct=True)")
    ap.add_argument("--metric", choices=["precomputed", "callable"], default="precomputed",
                    help="callable = literal Python metric (slow; for cross-checking only)")
    ap.add_argument("--max-images", type=int, default=None, help="evaluate only the first N expert images (smoke test)")
    ap.add_argument("--n-jobs", type=int, default=-1)
    a = ap.parse_args()

    from joblib import Parallel, delayed
    from paretoset import paretoset

    t0 = time.time()
    need = [a.image_col, "x", "y"]
    cit = pd.read_csv(a.citsci, usecols=lambda c: c in need)
    exp = pd.read_csv(a.expert, usecols=lambda c: c in need)
    for name, df in (("citsci", cit), ("expert", exp)):
        miss = [c for c in need if c not in df.columns]
        if miss:
            sys.exit(f"ERROR: {name} file lacks columns {miss}; has {list(df.columns)}")
    n_bad = int(cit[["x", "y"]].isna().any(axis=1).sum() + exp[["x", "y"]].isna().any(axis=1).sum())
    cit = cit.dropna(subset=["x", "y"])
    exp = exp.dropna(subset=["x", "y"])

    ms_list = parse_range(a.min_samples, "int")
    eps_list = parse_range(a.eps, "float")
    w_list = parse_range(a.shape_weight, "float")
    combos = list(itertools.product(w_list, eps_list, ms_list))  # same nesting as eval_image

    images = list(pd.unique(exp[a.image_col]))
    if a.max_images:
        images = images[: a.max_images]
    cit_groups = {k: g[["x", "y"]].to_numpy(float) for k, g in cit.groupby(a.image_col, sort=False)}
    exp_groups = {k: g[["x", "y"]].to_numpy(float) for k, g in exp.groupby(a.image_col, sort=False)}
    items = [(cit_groups.get(img), exp_groups[img]) for img in images]
    n_no_cit = sum(p is None for p, _ in items)
    print(f"images (expert): {len(images)}  without citizen points: {n_no_cit}  "
          f"citizen-only images ignored: {len(set(cit_groups) - set(exp_groups))}  rows dropped for NaN x/y: {n_bad}")
    print(f"grid: {len(ms_list)} min_samples x {len(eps_list)} eps x {len(w_list)} shape_weight = {len(combos)} combos")

    n_jobs = a.n_jobs if a.n_jobs != -1 else (os.cpu_count() or 1)
    n_chunks = max(1, min(len(items), n_jobs * 4))
    chunks = [items[i::n_chunks] for i in range(n_chunks)]
    args = (w_list, eps_list, ms_list, a.max_match_dist, a.metric)
    res = Parallel(n_jobs=n_jobs, backend="multiprocessing")(delayed(eval_chunk)(c, *args) for c in chunks)
    per_img = [r for chunk in res for r in chunk]
    F1 = np.vstack([r[0] for r in per_img])
    D = np.vstack([r[1] for r in per_img])

    mean_f1 = F1.mean(axis=0)
    with np.errstate(all="ignore"):
        cnt = (~np.isnan(D)).sum(axis=0)
        mean_d = np.where(cnt > 0, np.nansum(D, axis=0) / np.maximum(cnt, 1), np.nan)
    allr = pd.DataFrame({
        "F1": mean_f1, "delta": mean_d,
        "min_samples": [c[2] for c in combos], "epsilon": [c[1] for c in combos],
        "shape_weight": [c[0] for c in combos],
    })
    if a.all_results:
        allr.to_csv(a.all_results, index=False)

    kept = allr[(allr["F1"] > a.f1_threshold) & allr["delta"].notna()].reset_index(drop=True)
    print(f"combos with mean F1 > {a.f1_threshold}: {len(kept)} / {len(allr)}  "
          f"(best F1 {allr['F1'].max():.5f}, best delta {allr['delta'].min():.5f})")
    if kept.empty:
        pd.DataFrame(columns=["F1", "delta", "min_samples", "epsilon", "shape_weight"]).to_csv(a.out, index=False)
        print(f"WARNING: no combo passed the F1 filter; wrote header-only {a.out}")
        return

    mask_all = paretoset(kept[["F1", "delta"]], sense=["max", "min"], distinct=False)
    mask = mask_all if a.keep_ties else paretoset(kept[["F1", "delta"]], sense=["max", "min"], distinct=True)
    n_tie = int(mask_all.sum() - paretoset(kept[["F1", "delta"]], sense=["max", "min"], distinct=True).sum())
    front = kept[mask].copy()
    front["F1"] = front["F1"].round(5)
    front["delta"] = front["delta"].round(5)
    front["min_samples"] = front["min_samples"].astype(int)
    if (front["epsilon"] % 1 == 0).all():
        front["epsilon"] = front["epsilon"].astype(int)
    front["shape_weight"] = front["shape_weight"].round(1)
    front = front.sort_values(["F1", "delta"], ascending=[False, True])
    front.to_csv(a.out, index=False)
    print(f"tied duplicate frontier combos {'kept' if a.keep_ties else 'collapsed'}: {n_tie}")
    print(f"pareto points: {len(front)} -> {a.out}  ({time.time() - t0:.1f}s)")
    print(front.to_string(index=False))
    validate(a.out, a.f1_threshold)


def validate(path, thr):
    """Re-read the written CSV and check format + Pareto consistency."""
    df = pd.read_csv(path)
    errs = []
    if list(df.columns) != ["F1", "delta", "min_samples", "epsilon", "shape_weight"]:
        errs.append(f"header {list(df.columns)}")
    if df.isna().any().any():
        errs.append("NaN present")
    if not (df["F1"] > thr).all():
        errs.append(f"F1 <= {thr} present")
    g = df.groupby(["F1", "delta"]).size().reset_index().sort_values("F1", ascending=False)
    if not (g["delta"].diff().dropna() < 0).all() or g["F1"].duplicated().any():
        errs.append("dominated row present (delta must strictly fall as F1 falls)")
    if errs:
        sys.exit("VALIDATION FAILED: " + "; ".join(errs))
    print(f"VALIDATION OK: {len(df)} rows")


if __name__ == "__main__":
    main()
