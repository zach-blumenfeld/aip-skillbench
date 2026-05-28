"""3D step-response metrics for point-to-point drone flight.

Given an actual position trajectory `pos_actual` (shape ``(3, n)``), a fixed
target position `pos_target` (shape ``(3,)``), and a time vector ``t`` (shape
``(n,)``), compute scalar step-response metrics on the 3D Euclidean distance to
the target. Use this instead of running 1D ``stepinfo`` per axis whenever all
three position axes move simultaneously — the axes are coupled (thrust that
corrects ``x`` also affects ``y`` and ``z``) and per-axis numbers misrepresent
the true convergence.

Returned metrics (dict)
-----------------------
RiseTime          First time the distance to target is <= 10 percent of the
                  initial distance ``d0``. NaN if it is never reached.
SettlingTime      Last time the distance exceeds ``settling_threshold * d0``.
                  NaN if the trajectory never re-enters or never leaves the
                  settling band.
Overshoot_pct     After the drone first enters the settling band, the maximum
                  distance seen, expressed as a percentage of ``d0``. ``0.0`` if
                  the band is never entered.
SteadyStateError  Final 3D Euclidean distance ``dist[-1]`` in metres.

Edge cases
----------
- ``d0 < 1e-6`` (already at target, e.g. a hover-in-place command): all four
  metrics return 0.0 — there is no step to characterise.
- The settling band is ``settling_threshold * d0`` (default 0.02). For very
  short commands ``d0`` is small, so the band can be only a few centimetres
  wide; if the drone approaches the target without oscillating past it, the
  band is never entered and ``Overshoot_pct`` is 0.0 by definition.
- Overshoot is defined by **distance from the target**, not by crossing it on
  a single axis. The drone must physically move farther from the target after
  entering the settling band to register overshoot.

Not for
-------
- Pure single-axis steps (hover/takeoff/land on ``z`` only) — use the 1D
  ``stepinfo`` directly on the ``z`` signal.
- Circular / figure-eight / arbitrary trajectory tracking — there is no fixed
  "final target", so rise/settling/overshoot are not meaningful. Use RMS error
  or cumulative absolute error instead.
"""

from __future__ import annotations

from typing import Dict

import numpy as np

DEFAULT_SETTLING_THRESHOLD = 0.02
DEFAULT_RISE_FRACTION = 0.10
AT_TARGET_TOL = 1e-6


def stepinfo_3d(
    pos_actual: np.ndarray,
    pos_target: np.ndarray,
    t: np.ndarray,
    settling_threshold: float = DEFAULT_SETTLING_THRESHOLD,
) -> Dict[str, float]:
    """Compute 3D step-response metrics on the Euclidean distance to target.

    Parameters
    ----------
    pos_actual
        Actual position trajectory, shape ``(3, n)`` with rows ``[x, y, z]``.
        Typically ``actual_state_matrix[0:3, :]`` from the simulator.
    pos_target
        Target position, shape ``(3,)``. For a single-command flight this is
        the last waypoint, e.g. ``waypoints[0:3, -1]``.
    t
        Time vector, shape ``(n,)``, in seconds. Same length as the second
        axis of ``pos_actual``.
    settling_threshold
        Fraction of the initial distance that defines the settling band.
        Default 0.02 (2 percent) — matches the task verifier.

    Returns
    -------
    dict
        ``{'RiseTime', 'SettlingTime', 'Overshoot_pct', 'SteadyStateError'}``.
        Floats throughout. ``RiseTime`` / ``SettlingTime`` may be NaN when the
        respective event never occurs.
    """
    pos_actual = np.asarray(pos_actual, dtype=float)
    pos_target = np.asarray(pos_target, dtype=float).reshape(3)
    t = np.asarray(t, dtype=float)

    if pos_actual.ndim != 2 or pos_actual.shape[0] != 3:
        raise ValueError(
            f"pos_actual must have shape (3, n); got {pos_actual.shape}"
        )
    if pos_actual.shape[1] != t.shape[0]:
        raise ValueError(
            "pos_actual and t must have the same length along time axis; "
            f"got {pos_actual.shape[1]} samples vs {t.shape[0]} time points"
        )

    dist = np.linalg.norm(pos_actual - pos_target[:, None], axis=0)
    d0 = float(dist[0])

    if d0 < AT_TARGET_TOL:
        return {
            "RiseTime": 0.0,
            "SettlingTime": 0.0,
            "Overshoot_pct": 0.0,
            "SteadyStateError": float(dist[-1]),
        }

    rise_time = float("nan")
    rise_band = DEFAULT_RISE_FRACTION * d0
    for k in range(len(dist)):
        if dist[k] <= rise_band:
            rise_time = float(t[k])
            break

    band = settling_threshold * d0
    settling_time = float("nan")
    for k in range(len(dist) - 1, -1, -1):
        if dist[k] > band:
            settling_time = float(t[k])
            break

    in_band = False
    max_post_entry = 0.0
    for k in range(len(dist)):
        if not in_band and dist[k] <= band:
            in_band = True
        if in_band and dist[k] > max_post_entry:
            max_post_entry = float(dist[k])
    overshoot_pct = (max_post_entry / d0) * 100.0 if in_band else 0.0

    return {
        "RiseTime": rise_time,
        "SettlingTime": settling_time,
        "Overshoot_pct": overshoot_pct,
        "SteadyStateError": float(dist[-1]),
    }


if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        description="Compute 3D step-response metrics from saved trajectory arrays."
    )
    parser.add_argument("actual", help="Path to actual_trajectory.npy (shape (15, n) or (3, n)).")
    parser.add_argument("target", nargs=3, type=float, help="Target position x y z.")
    parser.add_argument(
        "--time-vec",
        help="Optional .npy path with the time vector. If omitted, --sample-rate is required.",
    )
    parser.add_argument(
        "--sample-rate",
        type=float,
        help="Sample rate (Hz) to synthesise a time vector when --time-vec is omitted.",
    )
    parser.add_argument(
        "--settling-threshold",
        type=float,
        default=DEFAULT_SETTLING_THRESHOLD,
        help="Settling band as a fraction of initial distance (default 0.02).",
    )
    args = parser.parse_args()

    actual = np.load(args.actual)
    if actual.ndim == 2 and actual.shape[0] >= 3:
        pos_actual = actual[0:3, :]
    else:
        raise SystemExit(f"Unexpected actual array shape {actual.shape}")

    if args.time_vec:
        t = np.load(args.time_vec)
    elif args.sample_rate:
        n = pos_actual.shape[1]
        t = np.arange(n) / args.sample_rate
    else:
        sys.exit("Provide --time-vec or --sample-rate so a time vector can be built.")

    metrics = stepinfo_3d(
        pos_actual,
        np.array(args.target),
        t,
        settling_threshold=args.settling_threshold,
    )
    json.dump(metrics, sys.stdout, indent=2)
    sys.stdout.write("\n")
