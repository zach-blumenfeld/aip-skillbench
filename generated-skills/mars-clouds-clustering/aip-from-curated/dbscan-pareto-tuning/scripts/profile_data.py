"""Resolve the config against defaults and profile both annotation CSVs.

stdin  : {"currentState": {"config": {...}}, "assets": {...}, "expects": [...]}
stdout : {"config": <resolved>, "profile": {...}, "config_problems": [...], "config_ok": bool}
CLI    : python profile_data.py --config cfg.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clustertune as ct  # noqa: E402

import pandas as pd  # noqa: E402

PROFILE_COLS = ["workflow_name", "tool_label", "tool", "frame", "channel", "user_name"]


def describe(path, cfg, filt, problems):
    out = {"path": path}
    if not os.path.exists(path):
        problems.append(f"file not found: {path}")
        return out, None
    header = pd.read_csv(path, nrows=0).columns.tolist()
    out["n_columns"] = len(header)
    want = [c for c in PROFILE_COLS if c in header]
    try:
        pts, dropped = ct.read_points(path, cfg, filt)
    except KeyError as exc:
        problems.append(exc.args[0] if exc.args else str(exc))
        return out, None
    extra = pd.read_csv(path, usecols=want + [cfg["frame_col"]], low_memory=False)
    out["n_rows_raw"] = int(len(extra))
    out["n_points_used"] = int(len(pts))
    out["n_rows_dropped_missing_xy"] = int(dropped)
    out["value_counts"] = {c: extra[c].astype(str).value_counts().head(8).to_dict() for c in want}
    per = pts.groupby("frame").size()
    out["n_frames"] = int(per.size)
    out["points_per_frame"] = {"min": int(per.min()) if len(per) else 0,
                               "median": float(per.median()) if len(per) else 0,
                               "max": int(per.max()) if len(per) else 0}
    if "user_name" in header:
        u = pd.read_csv(path, usecols=[cfg["frame_col"], "user_name"], low_memory=False)
        upf = u.groupby(cfg["frame_col"])["user_name"].nunique()
        out["users_per_frame"] = {"min": int(upf.min()), "median": float(upf.median()),
                                  "max": int(upf.max())}
    out["x_range"] = [float(pts["x"].min()), float(pts["x"].max())] if len(pts) else None
    out["y_range"] = [float(pts["y"].min()), float(pts["y"].max())] if len(pts) else None
    return out, pts


def run(state, assets):
    cfg = ct.merge_config(state.get("config"), assets)
    problems = []
    for key in ("citsci_csv", "expert_csv", "output_csv"):
        if not cfg.get(key):
            problems.append(f"config.{key} is empty")
    try:
        grids = {k: ct.expand_grid(cfg[k], as_int=(k == "min_samples"))
                 for k in ("min_samples", "epsilon", "shape_weight")}
        for w in grids["shape_weight"]:
            sx, sy = ct.scale_factors(cfg, w)
            if sx < 0 or sy < 0:
                problems.append(f"negative axis scale at w={w}: x={sx}, y={sy}")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"bad grid / scale expression: {exc}")
        grids = {}
    for key, allowed in (("frames", {"expert", "intersection", "union"}),
                         ("match_mode", {"assign_then_filter", "mask_then_assign"}),
                         ("f1_aggregation", {"per_image_mean", "global"}),
                         ("delta_aggregation", {"per_image_mean", "global_pairs"}),
                         ("centroid", {"mean", "median"})):
        if cfg.get(key) not in allowed:
            problems.append(f"config.{key}={cfg.get(key)!r} not in {sorted(allowed)}")

    cit_desc, cit = describe(cfg["citsci_csv"], cfg, cfg.get("citsci_filter"), problems)
    exp_desc, exp = describe(cfg["expert_csv"], cfg, cfg.get("expert_filter"), problems)
    profile = {"citsci": cit_desc, "expert": exp_desc,
               "grid_sizes": {k: len(v) for k, v in grids.items()},
               "grid_values": grids}
    if grids:
        profile["n_combinations"] = (len(grids["min_samples"]) * len(grids["epsilon"])
                                     * len(grids["shape_weight"]))
    if cit is not None and exp is not None:
        c, e = set(cit["frame"]), set(exp["frame"])
        profile["frame_overlap"] = {"citsci_only": len(c - e), "expert_only": len(e - c),
                                    "both": len(c & e)}
        if not (c & e):
            problems.append(f"no shared values in frame_col {cfg['frame_col']!r} between files")
        try:
            profile["n_frames_evaluated"] = len(ct.frames_to_evaluate(cit, exp, cfg["frames"]))
        except ValueError as exc:
            problems.append(str(exc))
    out_dir = os.path.dirname(os.path.abspath(cfg["output_csv"])) if cfg.get("output_csv") else ""
    if out_dir and not os.path.isdir(out_dir):
        problems.append(f"output directory does not exist: {out_dir}")
    return {"config": cfg, "profile": profile, "config_problems": problems,
            "config_ok": not problems}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    args = ap.parse_args()
    if args.config:
        with open(args.config) as fh:
            ct.emit(run({"config": json.load(fh)}, None))
    else:
        payload = ct.read_stdin()
        ct.emit(run(payload.get("currentState", {}), payload.get("assets")))
