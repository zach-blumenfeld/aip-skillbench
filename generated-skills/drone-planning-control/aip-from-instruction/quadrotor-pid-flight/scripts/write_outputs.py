"""Write the four required result artifacts with strict, schema-exact contents.

  - planned_trajectory.npy : (15, max_iter) float ndarray
  - actual_trajectory.npy  : (15, max_iter) float ndarray
  - metrics_3d.json        : exactly {mode, RiseTime, SettlingTime, Overshoot_pct, SteadyStateError}
  - tuning_results.json    : exactly {kp_pos, ki_pos, kd_pos, kp_att, ki_att, kd_att}
                             each a length-3 list of floats
"""
from __future__ import annotations

import json
import os

import numpy as np

METRIC_KEYS = ("mode", "RiseTime", "SettlingTime", "Overshoot_pct", "SteadyStateError")
GAIN_KEYS = ("kp_pos", "ki_pos", "kd_pos", "kp_att", "ki_att", "kd_att")


def write(planned: dict, actual: dict, metrics: dict, gains: dict,
          results_dir: str) -> str:
    os.makedirs(results_dir, exist_ok=True)

    M = np.asarray(planned["matrix"])
    A = np.asarray(actual["matrix"])
    if M.shape[0] != 15 or A.shape[0] != 15:
        raise ValueError(f"trajectory matrices must have 15 rows; got {M.shape}, {A.shape}")
    if M.shape != A.shape:
        raise ValueError(f"planned/actual shapes differ: {M.shape} vs {A.shape}")

    np.save(os.path.join(results_dir, "planned_trajectory.npy"), M.astype(float))
    np.save(os.path.join(results_dir, "actual_trajectory.npy"), A.astype(float))

    metrics_out = {k: metrics[k] for k in METRIC_KEYS}
    # mode stays a string; numeric fields cast to float
    for k in METRIC_KEYS[1:]:
        metrics_out[k] = float(metrics_out[k])
    with open(os.path.join(results_dir, "metrics_3d.json"), "w") as f:
        json.dump(metrics_out, f, indent=2)

    gains_out = {}
    for k in GAIN_KEYS:
        v = list(gains[k])
        if len(v) != 3:
            raise ValueError(f"gain {k!r} must be length-3, got length {len(v)}")
        gains_out[k] = [float(x) for x in v]
    with open(os.path.join(results_dir, "tuning_results.json"), "w") as f:
        json.dump(gains_out, f, indent=2)

    return results_dir
