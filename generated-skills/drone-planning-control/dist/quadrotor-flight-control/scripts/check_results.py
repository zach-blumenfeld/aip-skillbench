"""Independent check of /root/results against the task's success criteria.

Requires: Python >= 3.8, numpy, pyyaml.

Usage: python3 check_results.py --commands /root/commands --params /root/system_params.yaml --out /root/results
Checks, per command: every required file exists; JSON schemas exact; both .npy are
(15 x max_iter) and finite; planned accel within accel_limit_up/down/horiz at every
sample; per-sample |actual - planned| position error < 0.05 m; SteadyStateError <
0.05 m; Overshoot_pct < 5; metrics_3d.json agrees with metrics recomputed from
actual_trajectory.npy. Exit 1 on any failure.
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flight_plan_parser import parse_flight_plan  # noqa: E402
from stepinfo_3d import stepinfo_3d  # noqa: E402

METRIC_KEYS = ["mode", "RiseTime", "SettlingTime", "Overshoot_pct", "SteadyStateError"]
GAIN_KEYS = ["kp_pos", "ki_pos", "kd_pos", "kp_att", "ki_att", "kd_att"]
PLOTS = ["desired_vs_actual.png", "errors.png", "cumulative_errors.png"]


def check(label, cmd_path, out_dir, p):
    errs = []
    with open(cmd_path) as f:
        wp, wt, modes = parse_flight_plan(f.read())
    n = int(round((wt[-1] - wt[0]) * p["sample_rate"])) + 1
    for name in ["metrics_3d.json", "tuning_results.json", "planned_trajectory.npy", "actual_trajectory.npy"] + \
            [os.path.join("plots", x) for x in PLOTS]:
        if not os.path.isfile(os.path.join(out_dir, name)):
            errs.append(f"missing {name}")
    if errs:
        return errs
    met = json.load(open(os.path.join(out_dir, "metrics_3d.json")))
    if sorted(met) != sorted(METRIC_KEYS):
        errs.append(f"metrics keys {sorted(met)}")
    gains = json.load(open(os.path.join(out_dir, "tuning_results.json")))
    if sorted(gains) != sorted(GAIN_KEYS) or any(len(gains[k]) != 3 for k in GAIN_KEYS if k in gains):
        errs.append("tuning_results schema")
    des = np.load(os.path.join(out_dir, "planned_trajectory.npy"))
    act = np.load(os.path.join(out_dir, "actual_trajectory.npy"))
    for nm, arr in (("planned", des), ("actual", act)):
        if arr.shape != (15, n):
            errs.append(f"{nm} shape {arr.shape} != (15, {n})")
        if not np.all(np.isfinite(arr)):
            errs.append(f"{nm} has non-finite values")
    if errs:
        return errs
    az, ah = des[14], np.hypot(des[12], des[13])
    if az.max() > p["accel_limit_up"]:
        errs.append(f"az {az.max():.3f} > up limit {p['accel_limit_up']}")
    if az.min() < -p["accel_limit_down"]:
        errs.append(f"az {az.min():.3f} < -down limit {p['accel_limit_down']}")
    if ah.max() > p["accel_limit_horiz"]:
        errs.append(f"horizontal accel {ah.max():.3f} > {p['accel_limit_horiz']}")
    track = np.linalg.norm(act[0:3] - des[0:3], axis=0)
    if track.max() >= 0.05:
        errs.append(f"max per-step position error {track.max():.4f} m at t={np.argmax(track) / p['sample_rate']:.3f}s")
    t = wt[0] + np.arange(n) / p["sample_rate"]
    m = stepinfo_3d(act[0:3], wp[0:3, -1], t, settling_threshold=0.02)
    if met.get("SteadyStateError", 1) >= 0.05:
        errs.append(f"SteadyStateError {met.get('SteadyStateError')}")
    if met.get("Overshoot_pct", 100) >= 5:
        errs.append(f"Overshoot_pct {met.get('Overshoot_pct')}")
    for k in METRIC_KEYS[1:]:
        if k in met and abs(float(met[k]) - m[k]) > 1e-6:
            errs.append(f"{k} file={met[k]} recomputed={m[k]}")
    print(f"{label}: max_err={track.max():.4f} SSE={m['SteadyStateError']:.4f} OS={m['Overshoot_pct']:.2f}% "
          f"az=[{az.min():.2f},{az.max():.2f}] ah={ah.max():.2f}")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commands", default="/root/commands")
    ap.add_argument("--params", default="/root/system_params.yaml")
    ap.add_argument("--out", default="/root/results")
    a = ap.parse_args()
    p = yaml.safe_load(open(a.params))
    bad = 0
    files = sorted(glob.glob(os.path.join(a.commands, "*.txt")))
    for cmd in files:
        label = os.path.splitext(os.path.basename(cmd))[0]
        errs = check(label, cmd, os.path.join(a.out, label), p)
        if errs:
            bad += 1
            print(f"{label}: FAIL -> " + "; ".join(errs))
    print(f"\n{len(files) - bad}/{len(files)} result folders pass")
    sys.exit(1 if bad or not files else 0)


if __name__ == "__main__":
    main()
