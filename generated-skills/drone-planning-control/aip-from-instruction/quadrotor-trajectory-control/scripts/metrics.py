#!/usr/bin/env python3
"""Step-response metrics matching the required metrics_3d.json schema.

Inputs:
    planned (15, N), actual (15, N), dt: float, mode: one of
    {"takeoff","hover","land","fly"}, settling_threshold: float = 0.02.

Output dict matches:
    {"mode": <mode>, "RiseTime": float, "SettlingTime": float,
     "Overshoot_pct": float, "SteadyStateError": float}

Definitions (computed on the command's primary scalar response):

  - For "takeoff", "land": scalar = z(t).
  - For "fly": scalar = projection of actual position onto the
    planned displacement vector (so the response is monotonically
    increasing if the drone tracks correctly).
  - For "hover": there is no transient. RiseTime = 0; SettlingTime = 0;
    Overshoot_pct = 0; SteadyStateError = mean |pos - pos_des| over the
    final 10% of samples.

  RiseTime         : time to go from 10% to 90% of (y_final - y_initial)
                     using the *actual* response.
  SettlingTime     : last time |y(t) - y_final| / max(|y_final|,1) >
                     settling_threshold; 0 if never exceeds.
  Overshoot_pct    : 100 * max(0, peak_overshoot) / max(|step|, 1e-9)
                     where step = y_target - y_initial.
  SteadyStateError : |y_actual_end_mean - y_target|, where end_mean is
                     the mean of the final 10% of samples.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

import numpy as np


def _final_window(arr: np.ndarray, frac: float = 0.1) -> np.ndarray:
    n = arr.shape[-1]
    k = max(1, int(n * frac))
    return arr[..., -k:]


def _scalar_response(planned: np.ndarray, actual: np.ndarray,
                     mode: str) -> tuple[np.ndarray, float, float]:
    """Return (y_actual_1d, y_initial, y_target)."""
    if mode in ("takeoff", "land", "hover"):
        y_act = actual[2, :]
        y_init = planned[2, 0]
        y_tgt = planned[2, -1]
        return y_act, float(y_init), float(y_tgt)
    if mode == "fly":
        start = planned[0:3, 0]
        end = planned[0:3, -1]
        disp = end - start
        norm = np.linalg.norm(disp)
        if norm < 1e-9:
            # Degenerate "fly to same point" — treat as hover.
            y_act = np.linalg.norm(actual[0:3, :] - start[:, None], axis=0)
            return y_act, 0.0, 0.0
        unit = disp / norm
        y_act = (actual[0:3, :] - start[:, None]).T @ unit
        return y_act, 0.0, float(norm)
    raise ValueError(f"unknown mode {mode!r}")


def compute_metrics(planned: np.ndarray, actual: np.ndarray, dt: float,
                    mode: str, settling_threshold: float = 0.02) -> dict:
    if mode == "hover":
        err = np.linalg.norm(actual[0:3, :] - planned[0:3, :], axis=0)
        sse = float(np.mean(_final_window(err)))
        return {
            "mode": mode,
            "RiseTime": 0.0,
            "SettlingTime": 0.0,
            "Overshoot_pct": 0.0,
            "SteadyStateError": sse,
        }

    y, y0, y_tgt = _scalar_response(planned, actual, mode)
    step = y_tgt - y0
    N = y.size
    t = np.arange(N) * dt

    # Rise time
    if abs(step) < 1e-9:
        rise_time = 0.0
    else:
        lo = y0 + 0.1 * step
        hi = y0 + 0.9 * step
        sgn = 1.0 if step > 0 else -1.0
        idx_lo = np.where(sgn * (y - lo) >= 0)[0]
        idx_hi = np.where(sgn * (y - hi) >= 0)[0]
        rise_time = float(t[idx_hi[0]] - t[idx_lo[0]]) if (
            len(idx_lo) and len(idx_hi)) else float(t[-1])

    # Settling time — last time outside the band around y_tgt
    band = settling_threshold * max(abs(y_tgt), 1.0)
    outside = np.where(np.abs(y - y_tgt) > band)[0]
    settling_time = float(t[outside[-1]]) if len(outside) else 0.0

    # Overshoot (only positive overshoot of step direction)
    if step >= 0:
        peak = float(np.max(y))
        overshoot = max(0.0, peak - y_tgt)
    else:
        peak = float(np.min(y))
        overshoot = max(0.0, y_tgt - peak)
    overshoot_pct = 100.0 * overshoot / max(abs(step), 1e-9)

    # Steady-state error on final 10%
    sse = float(abs(np.mean(_final_window(y)) - y_tgt))

    return {
        "mode": mode,
        "RiseTime": rise_time,
        "SettlingTime": settling_time,
        "Overshoot_pct": overshoot_pct,
        "SteadyStateError": sse,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--planned", required=True)
    p.add_argument("--actual", required=True)
    p.add_argument("--dt", type=float, required=True)
    p.add_argument("--mode", required=True)
    p.add_argument("--settling_threshold", type=float, default=0.02)
    args = p.parse_args()
    planned = np.load(args.planned)
    actual = np.load(args.actual)
    out = compute_metrics(planned, actual, args.dt, args.mode,
                          args.settling_threshold)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
