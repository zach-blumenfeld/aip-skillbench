"""Shared logic: config, loading, weighted-distance DBSCAN, Hungarian matching, Pareto.

Runs with numpy / scipy / pandas / scikit-learn / joblib / paretoset only
(the task container's packages). Imported by profile_data.py and grid_search.py.
"""
import json
import math
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(HERE, "..", "assets", "default_config.json")


# ---------------------------------------------------------------- config ----

def load_defaults(assets=None):
    """Defaults come from the injected asset when run by `aip run`, else from disk."""
    if assets and "default_config" in assets:
        raw = assets["default_config"]
        return json.loads(raw) if isinstance(raw, str) else dict(raw)
    with open(DEFAULT_CONFIG) as fh:
        return json.load(fh)


def merge_config(config, assets=None):
    cfg = load_defaults(assets)
    for k, v in (config or {}).items():
        if v is not None:
            cfg[k] = v
    return cfg


def expand_grid(spec, as_int=False):
    """A list is used as-is; {start, stop, step} is an inclusive arithmetic range."""
    if isinstance(spec, (int, float)):
        vals = [spec]
    elif isinstance(spec, list):
        vals = list(spec)
    elif isinstance(spec, dict):
        start, stop, step = spec["start"], spec["stop"], spec["step"]
        n = int(math.floor((stop - start) / step + 1e-9)) + 1
        vals = [start + i * step for i in range(n)]
    else:
        raise ValueError(f"bad grid spec: {spec!r}")
    if as_int:
        return [int(round(v)) for v in vals]
    # round away float drift (0.9 + 3*0.1 -> 1.2, not 1.2000000000000002)
    return [round(float(v), 10) for v in vals]


def scale_factors(cfg, w):
    """Per-axis multipliers for the shape weight w, from the config's expressions."""
    env = {"w": w, "sqrt": math.sqrt, "abs": abs, "__builtins__": {}}
    sx = float(eval(str(cfg["x_scale"]), env))  # noqa: S307 - config-authored arithmetic
    sy = float(eval(str(cfg["y_scale"]), env))
    return sx, sy


def make_weighted_metric(sx, sy, p=2):
    """The custom-metric closure in the form sklearn/scipy accept (used for verification)."""
    def distance(a, b):
        dx = abs(a[0] - b[0]) * sx
        dy = abs(a[1] - b[1]) * sy
        if p == 2:
            return math.sqrt(dx * dx + dy * dy)
        return (dx ** p + dy ** p) ** (1.0 / p)
    return distance


# ----------------------------------------------------------------- data -----

def read_points(path, cfg, filt):
    cols = [cfg["frame_col"], cfg["x_col"], cfg["y_col"]] + [c for c in (filt or {})]
    header = pd.read_csv(path, nrows=0).columns.tolist()
    missing = [c for c in dict.fromkeys(cols) if c not in header]
    if missing:
        raise KeyError(f"{path}: missing columns {missing}; available: {header}")
    df = pd.read_csv(path, usecols=list(dict.fromkeys(cols)), low_memory=False)
    for col, allowed in (filt or {}).items():
        allowed = allowed if isinstance(allowed, list) else [allowed]
        df = df[df[col].astype(str).isin([str(a) for a in allowed])]
    df = df.rename(columns={cfg["frame_col"]: "frame", cfg["x_col"]: "x", cfg["y_col"]: "y"})
    df["x"] = pd.to_numeric(df["x"], errors="coerce")
    df["y"] = pd.to_numeric(df["y"], errors="coerce")
    n_before = len(df)
    df = df.dropna(subset=["frame", "x", "y"])
    return df[["frame", "x", "y"]].reset_index(drop=True), n_before - len(df)


def frames_to_evaluate(cit, exp, mode):
    c, e = set(cit["frame"].unique()), set(exp["frame"].unique())
    if mode == "expert":
        keep = e
    elif mode == "intersection":
        keep = c & e
    elif mode == "union":
        keep = c | e
    else:
        raise ValueError(f"frames must be expert|intersection|union, got {mode!r}")
    return sorted(keep)


def group_xy(df, frames):
    g = {f: grp[["x", "y"]].to_numpy(float) for f, grp in df.groupby("frame", sort=False)}
    empty = np.zeros((0, 2))
    return [g.get(f, empty) for f in frames]


# --------------------------------------------------------------- DBSCAN -----

def pairwise(points, sx, sy, p):
    if len(points) == 0:
        return np.zeros((0, 0))
    d = np.abs(points[:, None, :] - points[None, :, :]) * np.array([sx, sy])
    if p == 2:
        return np.sqrt((d ** 2).sum(-1))
    return ((d ** p).sum(-1)) ** (1.0 / p)


def dbscan_labels(adj, counts, min_samples):
    """sklearn DBSCAN semantics on a boolean eps-neighbourhood matrix (self included).

    Core: neighbourhood size (incl. self) >= min_samples. Clusters are connected
    components of core points; clusters are numbered by their lowest core index, and
    a border point takes the lowest-numbered adjacent cluster, which is what sklearn's
    in-order expansion produces. Noise = -1.
    """
    from scipy.sparse.csgraph import connected_components

    n = adj.shape[0]
    labels = np.full(n, -1, dtype=int)
    core = counts >= min_samples
    if not core.any():
        return labels
    ci = np.flatnonzero(core)
    _, comp = connected_components(adj[np.ix_(ci, ci)], directed=False)
    # renumber components by first appearance (lowest core index)
    order = {}
    for c in comp:
        if c not in order:
            order[c] = len(order)
    comp = np.array([order[c] for c in comp])
    labels[ci] = comp
    border = np.flatnonzero(~core & adj[:, ci].any(axis=1))
    for b in border:
        labels[b] = comp[adj[b, ci]].min()
    return labels


def centroids(points, labels, how="mean"):
    out = []
    for k in range(labels.max() + 1 if len(labels) else 0):
        m = points[labels == k]
        out.append(np.median(m, axis=0) if how == "median" else m.mean(axis=0))
    return np.array(out).reshape(-1, 2)


# ------------------------------------------------------------- matching -----

def match(pred, truth, max_dist, mode="assign_then_filter"):
    """Hungarian matching on plain Euclidean pixel distance. Returns matched distances."""
    from scipy.optimize import linear_sum_assignment
    from scipy.spatial.distance import cdist

    if len(pred) == 0 or len(truth) == 0:
        return np.zeros(0)
    cost = cdist(pred, truth)
    if mode == "mask_then_assign":
        big = max_dist * 1e6 + 1.0
        masked = np.where(cost <= max_dist, cost, big)
        r, c = linear_sum_assignment(masked)
    elif mode == "assign_then_filter":
        r, c = linear_sum_assignment(cost)
    else:
        raise ValueError(f"match_mode must be assign_then_filter|mask_then_assign, got {mode!r}")
    d = cost[r, c]
    return d[d <= max_dist]


def score_frame(pred, truth, cfg):
    d = match(pred, truth, cfg["match_max_distance"], cfg["match_mode"])
    tp = len(d)
    fp = len(pred) - tp
    fn = len(truth) - tp
    denom = 2 * tp + fp + fn
    f1 = (2 * tp / denom) if denom else 1.0  # nothing predicted, nothing expected
    return f1, tp, fp, fn, d


def aggregate(frame_scores, cfg):
    f1s = np.array([s[0] for s in frame_scores])
    tp = sum(s[1] for s in frame_scores)
    fp = sum(s[2] for s in frame_scores)
    fn = sum(s[3] for s in frame_scores)
    if cfg["f1_aggregation"] == "global":
        denom = 2 * tp + fp + fn
        f1 = 2 * tp / denom if denom else float("nan")
    else:
        f1 = float(f1s.mean()) if len(f1s) else float("nan")
    if cfg["delta_aggregation"] == "global_pairs":
        all_d = np.concatenate([s[4] for s in frame_scores]) if frame_scores else np.zeros(0)
        delta = float(all_d.mean()) if len(all_d) else float("nan")
    else:
        per = [s[4].mean() for s in frame_scores if len(s[4])]
        delta = float(np.mean(per)) if per else float("nan")
    return f1, delta, tp, fp, fn


def evaluate_weight(w, cit_frames, exp_frames, cfg):
    """All (min_samples, epsilon) combinations for one shape weight."""
    sx, sy = scale_factors(cfg, w)
    p = cfg["minkowski_p"]
    eps_list = expand_grid(cfg["epsilon"])
    ms_list = expand_grid(cfg["min_samples"], as_int=True)
    per_combo = {(ms, e): [] for ms in ms_list for e in eps_list}
    for pts, truth in zip(cit_frames, exp_frames):
        D = pairwise(pts, sx, sy, p)
        for e in eps_list:
            adj = D <= e
            counts = adj.sum(axis=1)
            for ms in ms_list:
                lab = dbscan_labels(adj, counts, ms) if len(pts) else np.zeros(0, int)
                pred = centroids(pts, lab, cfg["centroid"])
                per_combo[(ms, e)].append(score_frame(pred, truth, cfg))
    rows = []
    for (ms, e), scores in per_combo.items():
        f1, delta, tp, fp, fn = aggregate(scores, cfg)
        rows.append({"F1": f1, "delta": delta, "min_samples": ms, "epsilon": e,
                     "shape_weight": w, "TP": tp, "FP": fp, "FN": fn})
    return rows


def verify_against_sklearn(cit_frames, cfg, n_samples, seed=0):
    """Spot-check the fast DBSCAN against sklearn DBSCAN with the callable custom metric."""
    from sklearn.cluster import DBSCAN

    rng = np.random.default_rng(seed)
    ws = expand_grid(cfg["shape_weight"])
    eps_list = expand_grid(cfg["epsilon"])
    ms_list = expand_grid(cfg["min_samples"], as_int=True)
    nonempty = [i for i, f in enumerate(cit_frames) if len(f) > 0]
    mismatches = 0
    checked = 0
    for _ in range(min(n_samples, len(nonempty) * len(ws))):
        pts = cit_frames[nonempty[rng.integers(len(nonempty))]]
        w = ws[rng.integers(len(ws))]
        e = eps_list[rng.integers(len(eps_list))]
        ms = ms_list[rng.integers(len(ms_list))]
        sx, sy = scale_factors(cfg, w)
        D = pairwise(pts, sx, sy, cfg["minkowski_p"])
        adj = D <= e
        fast = dbscan_labels(adj, adj.sum(axis=1), ms)
        ref = DBSCAN(eps=e, min_samples=ms,
                     metric=make_weighted_metric(sx, sy, cfg["minkowski_p"])).fit(pts).labels_
        a = centroids(pts, fast, cfg["centroid"])
        b = centroids(pts, ref, cfg["centroid"])
        checked += 1
        if a.shape != b.shape or not np.allclose(a, b, atol=1e-6):
            mismatches += 1
    return checked, mismatches


# --------------------------------------------------------------- Pareto -----

def pareto_mask(df, distinct=True):
    try:
        from paretoset import paretoset
        return np.asarray(paretoset(df[["F1", "delta"]], sense=["max", "min"], distinct=distinct))
    except ImportError:  # manual fallback: keep points no other point dominates
        f1, de = df["F1"].to_numpy(), df["delta"].to_numpy()
        mask = np.ones(len(df), bool)
        for i in range(len(df)):
            dom = (f1 >= f1[i]) & (de <= de[i]) & ((f1 > f1[i]) | (de < de[i]))
            mask[i] = not dom.any()
        if distinct:
            seen = set()
            for i in np.flatnonzero(mask):
                key = (f1[i], de[i])
                if key in seen:
                    mask[i] = False
                seen.add(key)
        return mask


# ------------------------------------------------------------------- io -----

def read_stdin():
    raw = sys.stdin.read()
    return json.loads(raw) if raw.strip() else {}


def emit(obj):
    def clean(v):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return clean(float(v))
        if isinstance(v, dict):
            return {str(k): clean(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [clean(x) for x in v]
        return v
    sys.stdout.write(json.dumps(clean(obj)))
    sys.stdout.flush()
