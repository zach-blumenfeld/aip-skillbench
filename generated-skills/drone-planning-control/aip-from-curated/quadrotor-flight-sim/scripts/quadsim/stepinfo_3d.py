"""3D step-response metrics on Euclidean distance to the final target."""
import numpy as np


def stepinfo_3d(pos_actual, pos_target, t, settling_threshold=0.02):
    pos_actual = np.asarray(pos_actual, float)
    t = np.asarray(t, float)
    dist = np.linalg.norm(pos_actual - np.asarray(pos_target, float).reshape(3, 1), axis=0)
    d0 = float(dist[0])
    zero = {"RiseTime": 0.0, "SettlingTime": 0.0, "Overshoot_pct": 0.0, "SteadyStateError": 0.0}
    if d0 < 1e-6:  # already at the target (hover)
        return zero
    rise_idx = np.nonzero(dist <= 0.1 * d0)[0]
    rise = float(t[rise_idx[0]]) if rise_idx.size else float(t[-1])
    band = settling_threshold * d0
    out_idx = np.nonzero(dist > band)[0]
    settling = float(t[out_idx[-1]]) if out_idx.size else 0.0
    in_idx = np.nonzero(dist <= band)[0]
    overshoot = float(dist[in_idx[0]:].max() / d0 * 100.0) if in_idx.size else 0.0
    return {"RiseTime": rise, "SettlingTime": settling, "Overshoot_pct": overshoot,
            "SteadyStateError": float(dist[-1])}
