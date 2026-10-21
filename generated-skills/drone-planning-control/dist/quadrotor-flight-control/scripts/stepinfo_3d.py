"""3D step-response metrics on Euclidean distance to the final target.

Requires: Python >= 3.8, numpy.
"""
import numpy as np


def stepinfo_3d(pos_actual, pos_target, t, settling_threshold=0.02):
    """pos_actual (3,n), pos_target (3,), t (n,) -> dict of RiseTime, SettlingTime,
    Overshoot_pct, SteadyStateError."""
    pos_actual = np.asarray(pos_actual, dtype=float)
    t = np.asarray(t, dtype=float)
    dist = np.linalg.norm(pos_actual - np.asarray(pos_target, dtype=float).reshape(3, 1), axis=0)
    d0 = dist[0]
    if d0 < 1e-6:
        # Already at the target (hover): no step to characterise. SteadyStateError is
        # still the true final distance so drift is not hidden.
        return {"RiseTime": 0.0, "SettlingTime": 0.0, "Overshoot_pct": 0.0,
                "SteadyStateError": float(dist[-1])}
    rise = np.nonzero(dist <= 0.1 * d0)[0]
    rise_time = float(t[rise[0]]) if rise.size else float(t[-1])
    band = settling_threshold * d0
    outside = np.nonzero(dist > band)[0]
    settling_time = float(t[outside[-1]]) if outside.size else 0.0
    inside = np.nonzero(dist <= band)[0]
    overshoot = float(dist[inside[0]:].max() / d0 * 100.0) if inside.size else 0.0
    return {"RiseTime": rise_time, "SettlingTime": settling_time,
            "Overshoot_pct": overshoot, "SteadyStateError": float(dist[-1])}
