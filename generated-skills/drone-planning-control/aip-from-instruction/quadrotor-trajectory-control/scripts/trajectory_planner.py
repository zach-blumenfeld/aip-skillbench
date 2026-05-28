#!/usr/bin/env python3
"""Generate a (15, N) desired-state trajectory for one parsed command.

Row layout (matches /root/results/<id>/planned_trajectory.npy):
  0:3   position    [x, y, z]
  3:6   velocity    [vx, vy, vz]
  6:9   orientation [phi, theta, psi]   (yaw fixed at 0 for these commands)
  9:12  angular velocity [p, q, r]
 12:15  acceleration [ax, ay, az]

Profile: minimum-jerk quintic per axis with zero start/end velocity and
acceleration. Quintic basis:
    s(tau) = 10*tau**3 - 15*tau**4 + 6*tau**5,  tau = t/T  in [0, 1]
    s'(tau) gives the velocity scale; s''(tau) gives the accel scale.
    Peak |s'(tau)|  = 1.875  at tau=0.5
    Peak |s''(tau)| = 5.7735 at tau = (5 - sqrt(5))/10 and (5+sqrt(5))/10.

Per-axis acceleration limit feasibility check:
    a_peak[i] = 5.7735 * |Delta[i]| / T**2
For vertical (i=2), Delta>0 uses accel_limit_up, Delta<0 uses accel_limit_down.
For horizontal (i=0,1) uses accel_limit_horiz.

If the requested duration T_req would exceed any axis's accel limit, the
planner extends T to the minimum feasible value (T_min = sqrt(5.7735 *
|Delta_worst| / a_lim_worst)) and reports the extension in the returned
metadata. This guarantees the planned trajectory stays within accel
limits at every timestep.

Hover commands hold start state for T seconds with zero velocity / accel.

CLI:
    python trajectory_planner.py --mode takeoff --start 0,0,0 --end 0,0,5 \
        --T 3.0 --dt 0.01 --au 5 --ad 5 --ah 5 --out planned.npy
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass

import numpy as np

PEAK_VEL_SCALE = 1.875                 # max |s'(tau)| for the quintic basis
PEAK_ACC_SCALE = 10.0 / math.sqrt(3)   # ≈ 5.7735 — max |s''(tau)|


@dataclass
class PlanResult:
    desired: np.ndarray   # shape (15, N)
    dt: float
    T_used: float
    T_requested: float
    extended: bool
    max_accel_axis: list   # peak |a| per axis under the chosen T


def _min_duration(delta: np.ndarray, au: float, ad: float, ah: float) -> float:
    """Return the smallest T such that peak |accel| per axis <= its limit."""
    dx, dy, dz = float(delta[0]), float(delta[1]), float(delta[2])
    # z-axis: use up-limit if rising, down-limit if descending
    az_lim = au if dz >= 0 else ad
    candidates = []
    if abs(dx) > 0:
        candidates.append(math.sqrt(PEAK_ACC_SCALE * abs(dx) / ah))
    if abs(dy) > 0:
        candidates.append(math.sqrt(PEAK_ACC_SCALE * abs(dy) / ah))
    if abs(dz) > 0:
        candidates.append(math.sqrt(PEAK_ACC_SCALE * abs(dz) / az_lim))
    return max(candidates) if candidates else 0.0


def _quintic_profile(T: float, dt: float):
    """Return (t, s, sd, sdd) on [0, T] inclusive of T."""
    N = max(2, int(math.ceil(T / dt)) + 1)
    t = np.linspace(0.0, T, N)
    tau = t / T if T > 0 else np.zeros_like(t)
    s = 10 * tau**3 - 15 * tau**4 + 6 * tau**5
    sd = (30 * tau**2 - 60 * tau**3 + 30 * tau**4) / max(T, 1e-9)
    sdd = (60 * tau - 180 * tau**2 + 120 * tau**3) / max(T**2, 1e-9)
    return t, s, sd, sdd


def plan_trajectory(
    mode: str,
    start: np.ndarray,
    end: np.ndarray,
    T_req: float,
    dt: float,
    accel_limit_up: float,
    accel_limit_down: float,
    accel_limit_horiz: float,
) -> PlanResult:
    """Plan a (15, N) trajectory honoring the per-axis accel limits."""
    start = np.asarray(start, dtype=float).reshape(3)
    end = np.asarray(end, dtype=float).reshape(3)
    delta = end - start

    if mode == "hover":
        N = max(2, int(math.ceil(T_req / dt)) + 1)
        des = np.zeros((15, N))
        des[0, :] = start[0]
        des[1, :] = start[1]
        des[2, :] = start[2]
        return PlanResult(des, dt, T_req, T_req, False, [0.0, 0.0, 0.0])

    T_min = _min_duration(delta, accel_limit_up, accel_limit_down,
                          accel_limit_horiz)
    extended = T_req < T_min
    # 1% safety margin so numerical jitter doesn't tip a planned sample
    # over the hard limit.
    T_used = max(T_req, T_min * 1.01) if T_min > 0 else T_req
    t, s, sd, sdd = _quintic_profile(T_used, dt)
    N = t.size
    des = np.zeros((15, N))
    for i in range(3):
        des[i, :] = start[i] + delta[i] * s
        des[3 + i, :] = delta[i] * sd
        des[12 + i, :] = delta[i] * sdd
    # Orientation, angular velocity: leave zero — the controller fills in
    # the desired roll/pitch implied by horizontal accel demand.
    max_a = [float(np.max(np.abs(des[12 + i, :]))) for i in range(3)]
    return PlanResult(des, dt, T_used, T_req, extended, max_a)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", required=True, choices=["takeoff", "hover", "land", "fly"])
    p.add_argument("--start", required=True, help="x,y,z")
    p.add_argument("--end", required=True, help="x,y,z")
    p.add_argument("--T", type=float, required=True)
    p.add_argument("--dt", type=float, default=0.01)
    p.add_argument("--au", type=float, required=True, help="accel_limit_up")
    p.add_argument("--ad", type=float, required=True, help="accel_limit_down")
    p.add_argument("--ah", type=float, required=True, help="accel_limit_horiz")
    p.add_argument("--out", default=None, help="optional .npy output path")
    args = p.parse_args()

    s = np.array([float(x) for x in args.start.split(",")])
    e = np.array([float(x) for x in args.end.split(",")])
    res = plan_trajectory(args.mode, s, e, args.T, args.dt,
                          args.au, args.ad, args.ah)
    if args.out:
        np.save(args.out, res.desired)
    print(json.dumps({
        "T_requested": res.T_requested,
        "T_used": res.T_used,
        "extended": res.extended,
        "N": int(res.desired.shape[1]),
        "max_accel_axis": res.max_accel_axis,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
