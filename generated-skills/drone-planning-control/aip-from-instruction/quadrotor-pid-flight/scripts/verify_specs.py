"""Recheck the four task success constraints after outputs are written.

Constraints:
  1. SteadyStateError < 0.05 m
  2. Overshoot_pct < 5%
  3. Planned trajectory within physical accel limits at EVERY timestep
  4. Per-timestep Euclidean position error < 0.05 m

Returns {passed: bool, failures: list[str]}.
"""
from __future__ import annotations

import numpy as np


def verify(planned: dict, actual: dict, metrics: dict, params: dict) -> dict:
    M = np.asarray(planned["matrix"])
    A = np.asarray(actual["matrix"])
    failures: list[str] = []

    # 1. SSE
    if metrics["SteadyStateError"] >= 0.05:
        failures.append(
            f"SteadyStateError {metrics['SteadyStateError']:.4f} m >= 0.05 m"
        )

    # 2. Overshoot
    if metrics["Overshoot_pct"] >= 5.0:
        failures.append(f"Overshoot_pct {metrics['Overshoot_pct']:.2f} >= 5")

    # 3. Planned accel limits
    a = M[12:15]
    horiz = np.linalg.norm(a[0:2], axis=0)
    az = a[2]
    h_max = float(horiz.max())
    az_up = float(max(0.0, az.max()))
    az_dn = float(max(0.0, -az.min()))
    if h_max > params["accel_limit_horiz"]:
        failures.append(
            f"planned horiz accel {h_max:.3f} > limit {params['accel_limit_horiz']}"
        )
    if az_up > params["accel_limit_up"]:
        failures.append(
            f"planned az up {az_up:.3f} > limit {params['accel_limit_up']}"
        )
    if az_dn > params["accel_limit_down"]:
        failures.append(
            f"planned az down {az_dn:.3f} > limit {params['accel_limit_down']}"
        )

    # 4. Per-timestep Euclidean pos error
    err = np.linalg.norm(M[0:3] - A[0:3], axis=0)
    if err.max() >= 0.05:
        failures.append(
            f"max per-timestep pos error {err.max():.4f} m >= 0.05 m"
        )

    return {"passed": not failures, "failures": failures}
