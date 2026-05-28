"""Quintic minimum-jerk trajectory planner clamped to system accel limits.

Produces a (15, max_iter) matrix with rows:
  0:3   position     [x, y, z]
  3:6   velocity     [vx, vy, vz]
  6:9   orientation  [phi, theta, psi]    (kept at 0; controller derives roll/pitch)
  9:12  angular vel  [p, q, r]            (kept at 0)
  12:15 acceleration [ax, ay, az]

The simulation horizon is `command_duration + settle_pad` so step-response
metrics (rise/settle/overshoot/SSE) have time to converge.
"""
from __future__ import annotations

import numpy as np

# Quintic s(tau) = 10 tau^3 - 15 tau^4 + 6 tau^5,  tau in [0,1], rest -> rest.
# Peak |d^2 s / d tau^2| = 10/sqrt(3) at tau = 0.5.
PEAK_S_DDOT = 10.0 / np.sqrt(3.0)  # ~= 5.7735


def _s(tau: np.ndarray) -> np.ndarray:
    return 10 * tau**3 - 15 * tau**4 + 6 * tau**5


def _sdot(tau: np.ndarray) -> np.ndarray:
    return 30 * tau**2 - 60 * tau**3 + 30 * tau**4


def _sddot(tau: np.ndarray) -> np.ndarray:
    return 60 * tau - 180 * tau**2 + 120 * tau**3


def settle_pad(t_cmd: float) -> float:
    """Extra simulation past the commanded end time, in seconds."""
    return max(3.0, 0.5 * t_cmd)


def feasibility_check(p0, p1, T, params) -> dict:
    """Return {ok, peak_horiz, peak_z, T_min_required}.

    The quintic minimum-jerk profile has *equal* positive and negative
    accel peaks (one during the accel phase, one during the decel phase),
    each of magnitude PEAK_S_DDOT * |delta| / T^2.

    So for a vertical move we must respect BOTH `accel_limit_up` (positive
    peak) and `accel_limit_down` (negative peak), regardless of the net
    direction of travel. The peak that's tightest sets `T_min_required`.
    """
    p0 = np.asarray(p0, float)
    p1 = np.asarray(p1, float)
    delta = p1 - p0
    peak_horiz = PEAK_S_DDOT * np.linalg.norm(delta[:2]) / T**2
    peak_z = PEAK_S_DDOT * abs(delta[2]) / T**2

    ratios = []
    if peak_horiz > 0:
        ratios.append(peak_horiz / params["accel_limit_horiz"])
    if peak_z > 0:
        ratios.append(peak_z / params["accel_limit_up"])
        ratios.append(peak_z / params["accel_limit_down"])
    worst = max(ratios) if ratios else 0.0
    ok = worst <= 1.0
    T_min = T * float(np.sqrt(worst)) if worst > 0 else 0.0
    return {
        "ok": bool(ok),
        "peak_horiz": float(peak_horiz),
        "peak_z": float(peak_z),
        "accel_limit_up": float(params["accel_limit_up"]),
        "accel_limit_down": float(params["accel_limit_down"]),
        "accel_limit_horiz": float(params["accel_limit_horiz"]),
        "T_min_required": float(T_min),
    }


def plan(command: dict, params: dict, pad: float | None = None) -> dict:
    dt = params["dt"]
    mode = command["mode"]

    if mode == "takeoff":
        p0 = np.array([0.0, 0.0, 0.0])
        p1 = np.array([0.0, 0.0, float(command["h"])])
        T = float(command["t"])
    elif mode == "land":
        p0 = np.array([0.0, 0.0, float(command["h"])])
        p1 = np.array([0.0, 0.0, 0.0])
        T = float(command["t"])
    elif mode == "hover":
        p0 = p1 = np.array([0.0, 0.0, float(command["h"])])
        T = float(command["t"])
    elif mode == "fly":
        p0 = np.array(command["p0"], dtype=float)
        p1 = np.array(command["p1"], dtype=float)
        T = float(command["t"])
    else:
        raise ValueError(f"unknown mode: {mode}")

    if mode != "hover":
        chk = feasibility_check(p0, p1, T, params)
        if not chk["ok"]:
            raise ValueError(
                f"Requested T={T}s violates accel limits "
                f"(peak_horiz={chk['peak_horiz']:.3f}, peak_z={chk['peak_z']:.3f}, "
                f"need T >= {chk['T_min_required']:.3f}s)."
            )

    pad_s = settle_pad(T) if pad is None else float(pad)
    T_total = T + pad_s
    N = int(np.round(T_total / dt)) + 1

    M = np.zeros((15, N), dtype=float)
    ts = np.arange(N) * dt

    # broadcast where possible
    inside = ts < T
    tau = np.zeros(N)
    if mode != "hover":
        tau[inside] = ts[inside] / T
    s = _s(tau)
    sd = _sdot(tau) / max(T, 1e-9)
    sdd = _sddot(tau) / max(T, 1e-9) ** 2

    delta = p1 - p0
    for k in range(N):
        if mode == "hover" or not inside[k]:
            M[0:3, k] = p1
            # vel/acc remain 0
        else:
            M[0:3, k] = p0 + delta * s[k]
            M[3:6, k] = delta * sd[k]
            M[12:15, k] = delta * sdd[k]

    return {
        "matrix": M,
        "dt": dt,
        "max_iter": N,
        "t_cmd": T,
        "t_total": T_total,
        "p0": p0.tolist(),
        "p1": p1.tolist(),
    }
