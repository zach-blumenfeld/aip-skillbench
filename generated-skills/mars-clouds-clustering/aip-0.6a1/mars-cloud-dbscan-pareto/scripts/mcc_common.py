"""Shared helpers for the mars-cloud-dbscan-pareto scripts (stdin/stdout JSON, config, CSV loading)."""
import json
import os
import sys

import numpy as np
import pandas as pd


def read_payload():
    payload = json.load(sys.stdin)
    return payload.get("state", {}), payload.get("assets", {}) or {}


def load_config(assets):
    raw = assets.get("config")
    if raw is None:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "config.json")) as fh:
            return json.load(fh)
    return json.loads(raw) if isinstance(raw, str) else raw


def emit(obj):
    json.dump(obj, sys.stdout, allow_nan=False)
    sys.stdout.write("\n")


def fail(msg):
    sys.stderr.write(f"ERROR: {msg}\n")
    sys.exit(1)


def load_points(path, cfg, label):
    """Read only the image key and x/y columns; the image key is kept as a string
    (values like '080109120000/080110120000_A3.png' must never be parsed as numbers)."""
    key, xc, yc = cfg["image_key"], cfg["x_col"], cfg["y_col"]
    if not os.path.isfile(path):
        fail(f"{label} file not found: {path}")
    header = pd.read_csv(path, nrows=0).columns.tolist()
    missing = [c for c in (key, xc, yc) if c not in header]
    if missing:
        fail(f"{label} file {path} lacks required column(s) {missing}; has {header[:60]}")
    df = pd.read_csv(path, usecols=[key, xc, yc], dtype={key: str}, low_memory=False)
    n_raw = len(df)
    df[key] = df[key].astype(str).str.strip()
    df[xc] = pd.to_numeric(df[xc], errors="coerce")
    df[yc] = pd.to_numeric(df[yc], errors="coerce")
    bad = df[xc].isna() | df[yc].isna() | df[key].isin(["", "nan", "None"])
    df = df.loc[~bad].reset_index(drop=True)
    return df, n_raw, int(bad.sum())


def resolve_search_space(user_space, cfg):
    """Merge the caller's search space over the task default and normalise types."""
    space = dict(cfg["default_search_space"])
    for k, v in (user_space or {}).items():
        if k not in space:
            fail(f"unknown search_space key {k!r}; allowed: {sorted(space)}")
        if v is not None and v != []:
            space[k] = v
    try:
        ms = sorted({int(v) for v in space["min_samples"]})
        eps = sorted({int(v) if float(v).is_integer() else float(v) for v in space["epsilon"]})
        sw = sorted({round(float(v), cfg["shape_weight_decimals"]) for v in space["shape_weight"]})
    except (TypeError, ValueError) as exc:
        fail(f"search_space values must be numeric lists: {exc}")
    if any(v < 1 for v in ms):
        fail("min_samples values must be >= 1")
    if any(v <= 0 for v in eps):
        fail("epsilon values must be > 0")
    if any(not (0 < w < 2) for w in sw):
        fail("shape_weight values must lie strictly between 0 and 2 (both axis weights w and 2-w positive)")
    return {"min_samples": ms, "epsilon": eps, "shape_weight": sw}


def group_points(df, cfg):
    key, xc, yc = cfg["image_key"], cfg["x_col"], cfg["y_col"]
    return {k: g[[xc, yc]].to_numpy(dtype=np.float64) for k, g in df.groupby(key, sort=False)}
