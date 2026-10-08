"""Grid-search DBSCAN (weighted distance) against expert points, write the Pareto frontier.

stdin  : {"currentState": {"config": {...}}, "assets": {...}, "expects": [...]}
stdout : {"output_csv", "pareto_rows", "n_combinations", "n_after_f1_filter",
          "best_f1_row", "best_delta_row", "verification", "summary"}
CLI    : python grid_search.py --config cfg.json
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clustertune as ct  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def run(state, assets):
    t0 = time.time()
    cfg = ct.merge_config(state.get("config"), assets)
    cit, _ = ct.read_points(cfg["citsci_csv"], cfg, cfg.get("citsci_filter"))
    exp, _ = ct.read_points(cfg["expert_csv"], cfg, cfg.get("expert_filter"))
    frames = ct.frames_to_evaluate(cit, exp, cfg["frames"])
    cit_frames = ct.group_xy(cit, frames)
    exp_frames = ct.group_xy(exp, frames)

    checked, mism = ct.verify_against_sklearn(cit_frames, cfg, int(cfg.get("verify_samples", 0)))
    if mism:
        raise RuntimeError(f"fast DBSCAN disagrees with sklearn on {mism}/{checked} samples")

    weights = ct.expand_grid(cfg["shape_weight"])
    try:
        from joblib import Parallel, delayed
        chunks = Parallel(n_jobs=cfg.get("n_jobs", -1))(
            delayed(ct.evaluate_weight)(w, cit_frames, exp_frames, cfg) for w in weights)
    except ImportError:
        chunks = [ct.evaluate_weight(w, cit_frames, exp_frames, cfg) for w in weights]
    res = pd.DataFrame([r for ch in chunks for r in ch])
    # deterministic grid order: min_samples, epsilon, shape_weight (itertools.product order)
    res = res.sort_values(["min_samples", "epsilon", "shape_weight"]).reset_index(drop=True)
    if cfg.get("all_results_csv"):
        res.to_csv(cfg["all_results_csv"], index=False)

    valid = res.dropna(subset=["F1", "delta"])
    thr = cfg.get("f1_min")
    if thr is not None:
        valid = valid[valid["F1"] >= thr] if cfg.get("f1_min_inclusive") else valid[valid["F1"] > thr]
    valid = valid.reset_index(drop=True)
    if valid.empty:
        front = valid
    else:
        front = valid[ct.pareto_mask(valid, cfg.get("pareto_distinct", True))]
        ties = int(ct.pareto_mask(valid, False).sum() - len(front))
    front = front.sort_values(cfg.get("sort_by", "F1"),
                              ascending=cfg.get("sort_ascending", False), kind="mergesort")

    nd = cfg.get("round_decimals")
    out = front.copy()
    if nd is not None:
        out["F1"] = out["F1"].round(nd)
        out["delta"] = out["delta"].round(nd)
    out["shape_weight"] = out["shape_weight"].round(10)
    for c in ("epsilon", "shape_weight"):  # print 22, not 22.0, when the grid is integral
        if len(res) and (res[c] % 1 == 0).all():
            out[c] = out[c].astype(int)
    out["min_samples"] = out["min_samples"].astype(int)
    cols = cfg.get("output_columns") or list(out.columns)
    missing = [c for c in cols if c not in out.columns]
    if missing:
        raise KeyError(f"output_columns {missing} not computed; available {list(out.columns)}")
    out[cols].to_csv(cfg["output_csv"], index=False)

    rows = out[cols].to_dict("records")
    def row(i):
        r = res.loc[i].to_dict()
        for k in ("min_samples", "TP", "FP", "FN"):
            r[k] = int(r[k])
        return r
    best_f1 = row(res["F1"].idxmax()) if res["F1"].notna().any() else None
    best_d = row(res["delta"].idxmin()) if res["delta"].notna().any() else None
    summary = (f"{len(res)} combinations over {len(frames)} frames; {len(valid)} pass the F1 "
               f"filter; {len(out)} Pareto-optimal rows written to {cfg['output_csv']} "
               f"in {time.time() - t0:.1f}s")
    return {
        "output_csv": cfg["output_csv"],
        "pareto_rows": rows,
        "n_combinations": int(len(res)),
        "n_frames_evaluated": len(frames),
        "n_after_f1_filter": int(len(valid)),
        "pareto_duplicate_ties_dropped": ties if not valid.empty else 0,
        "best_f1_row": best_f1,
        "best_delta_row": best_d,
        "verification": {"sklearn_spot_checks": checked, "mismatches": mism},
        "summary": summary,
    }


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
