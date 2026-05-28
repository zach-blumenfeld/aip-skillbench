"""Mode-aware step-response metrics for drone command-following.

settling_threshold defaults to 0.02 and is treated as a fraction of step size
(the industry-standard "2% band" interpretation of `settling_threshold=0.02`).

Output fields are exactly the four required by the task spec:
  mode, RiseTime, SettlingTime, Overshoot_pct, SteadyStateError.
"""
from __future__ import annotations

import numpy as np


def _pick_axis(planned_matrix: np.ndarray, mode: str) -> int:
    """Pick the axis used for step-response metrics."""
    if mode in ("takeoff", "hover", "land"):
        return 2  # z
    # for 'fly': the axis with the largest commanded displacement
    deltas = np.ptp(planned_matrix[0:3], axis=1)
    return int(np.argmax(deltas))


def _step_metrics(ref: np.ndarray, act: np.ndarray, dt: float,
                  threshold_frac: float) -> tuple[float, float, float, float]:
    """Return (RiseTime, SettlingTime, Overshoot_pct, SteadyStateError)."""
    final = float(ref[-1])
    initial = float(ref[0])
    step_mag = abs(final - initial)
    # for hover (no step) use the actual deviation magnitude as denominator
    denom = step_mag if step_mag > 1e-6 else max(np.ptp(act), 1e-6)

    direction = 1.0 if final >= initial else -1.0

    # rise time: 10% -> 90% of step on the ACTUAL signal
    p10 = initial + 0.1 * (final - initial)
    p90 = initial + 0.9 * (final - initial)

    def first_cross(signal: np.ndarray, level: float) -> int:
        if direction > 0:
            mask = signal >= level
        else:
            mask = signal <= level
        idxs = np.where(mask)[0]
        return int(idxs[0]) if len(idxs) > 0 else -1

    if step_mag > 1e-6:
        i10 = first_cross(act, p10)
        i90 = first_cross(act, p90)
        rise = (i90 - i10) * dt if i10 >= 0 and i90 > i10 else 0.0
    else:
        rise = 0.0

    # overshoot %: max excursion past final in the step direction
    if direction > 0:
        peak = float(act.max())
        over = (peak - final) / denom * 100.0
    else:
        peak = float(act.min())
        over = (final - peak) / denom * 100.0
    over = max(0.0, over)

    # settling time: last index where |act - final| > band, +1 step => time
    band = threshold_frac * denom
    outside = np.where(np.abs(act - final) > band)[0]
    settle = (float(outside[-1]) + 1.0) * dt if len(outside) > 0 else 0.0

    # steady-state error: mean |act - final| over the last 0.5 s
    n_last = max(1, int(round(0.5 / dt)))
    ss = float(np.mean(np.abs(act[-n_last:] - final)))

    return float(rise), float(settle), float(over), float(ss)


def compute_metrics(planned: dict, actual: dict, command: dict,
                    settling_threshold: float = 0.02) -> dict:
    M = planned["matrix"]
    A = actual["matrix"]
    dt = planned["dt"]
    mode = command["mode"]
    axis = _pick_axis(M, mode)
    rise, settle, over, ss = _step_metrics(M[axis], A[axis], dt, settling_threshold)
    return {
        "mode": mode,
        "RiseTime": rise,
        "SettlingTime": settle,
        "Overshoot_pct": over,
        "SteadyStateError": ss,
    }
