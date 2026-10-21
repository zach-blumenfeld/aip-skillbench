"""Waypoints + modes -> (15 x max_iter) desired state matrix.

Requires: Python >= 3.8, numpy, scipy.

Rows: 0:3 pos, 3:6 vel, 6:9 orientation [phi, theta, psi], 9:12 angular velocity,
12:15 acceleration. Each non-hover segment is a clamped cubic spline (zero velocity
at both ends of the segment); hover segments hold position with zero vel/acc.
Roll/pitch rows are the small-angle attitude needed to produce the planned
horizontal acceleration (same formula as attitude_planner).

Acceleration limits: a clamped cubic peaks at 6L/T^2 (at both segment ends). If
accel_limits=(up, down, horiz) is given and the cubic would exceed them, the segment
switches to an accelerate-coast-decelerate profile along the same straight line
with the smallest peaks that finish on time (speed-up and braking accelerations
scaled to their own directional limits, +2% margin). If even that exceeds
the limits the command is infeasible in the requested time: the profile is kept
and check_accel_limits reports the violation.
"""
import numpy as np
from scipy.interpolate import CubicSpline


def num_samples(waypoint_times, sample_rate):
    """max_iter: samples from t0 to time_final inclusive."""
    return int(round((waypoint_times[-1] - waypoint_times[0]) * sample_rate)) + 1


class WaypointTrajectory:
    """Callable that steps through the piecewise spline one sample per call.

    Returns (pos, quaternion[w,x,y,z], vel, acc, zeros(3)) and advances t by dt.
    """

    def __init__(self, waypoints, waypoint_times, sample_rate, modes, accel_limits=None):
        self.wp = np.asarray(waypoints, dtype=float)
        self.wt = np.asarray(waypoint_times, dtype=float)
        self.modes = list(modes)
        if self.wp.shape[1] != len(self.wt) or len(self.modes) != len(self.wt) - 1:
            raise ValueError("need n waypoints, n times, n-1 modes")
        if np.any(np.diff(self.wt) <= 0):
            raise ValueError("waypoint_times must be strictly increasing")
        self.dt = 1.0 / sample_rate
        self.t_current = self.wt[0]
        self.splines = []
        self.profiles = []
        for i, mode in enumerate(self.modes):
            t0, t1 = self.wt[i], self.wt[i + 1]
            if mode == "hover":
                self.splines.append(None)
                self.profiles.append("hold")
                continue
            p0, p1 = self.wp[0:3, i], self.wp[0:3, i + 1]
            L, T = float(np.linalg.norm(p1 - p0)), t1 - t0
            A1 = A2 = np.inf
            if L > 0 and accel_limits:
                u = (p1 - p0) / L
                A1, A2 = _dir_limit(u, accel_limits), _dir_limit(-u, accel_limits)  # speed up / brake
            if 6.0 * L / T ** 2 > min(A1, A2):
                yaw = CubicSpline([t0, t1], self.wp[3, i:i + 2], bc_type="clamped")
                k = 1.02 * 2.0 * L * (1.0 / A1 + 1.0 / A2) / T ** 2  # smallest feasible scale + 2%
                self.splines.append(("trap", p0, p1, L, t0, T, k * A1, k * A2, yaw))
                self.profiles.append("trapezoid")
            else:
                # bc 'clamped' = zero velocity at segment ends. A 2-point default
                # spline would be a straight line (constant velocity, step at t0).
                pos = CubicSpline([t0, t1], self.wp[0:3, i:i + 2].T, bc_type="clamped")
                yaw = CubicSpline([t0, t1], self.wp[3, i:i + 2], bc_type="clamped")
                self.splines.append((pos, yaw))
                self.profiles.append("cubic")

    def evaluate(self, t):
        i = int(np.clip(np.searchsorted(self.wt, t, side="right") - 1, 0, len(self.modes) - 1))
        t = min(max(t, self.wt[0]), self.wt[-1])
        if self.splines[i] is None:
            p = self.wp[0:3, i].copy()
            return p, np.zeros(3), np.zeros(3), self.wp[3, i], 0.0
        if self.splines[i][0] == "trap":
            _, p0, p1, L, t0, T, a1, a2, ys = self.splines[i]
            s, v, acc = _trapezoid(t - t0, L, T, a1, a2)
            u = (p1 - p0) / L
            return p0 + s * u, v * u, acc * u, float(ys(t)), float(ys(t, 1))
        ps, ys = self.splines[i]
        return ps(t), ps(t, 1), ps(t, 2), float(ys(t)), float(ys(t, 1))

    def __call__(self):
        pos, vel, acc, yaw, _ = self.evaluate(self.t_current)
        self.t_current += self.dt
        quat = np.array([np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2)])
        return pos, quat, vel, acc, np.zeros(3)


def _dir_limit(u, limits):
    """Largest acceleration magnitude along unit vector u within (up, down, horiz)."""
    up, down, horiz = limits
    c = [horiz / np.hypot(u[0], u[1])] if np.hypot(u[0], u[1]) > 1e-12 else []
    if u[2] > 1e-12:
        c.append(up / u[2])
    elif u[2] < -1e-12:
        c.append(down / -u[2])
    return min(c) if c else np.inf


def _trapezoid(tau, L, T, a1, a2):
    """Accelerate at a1, coast, brake at a2; covers L in T. Returns (s, v, acc)."""
    c = 0.5 * (1.0 / a1 + 1.0 / a2)
    v = (T - np.sqrt(max(T * T - 4.0 * c * L, 0.0))) / (2.0 * c)  # coast speed
    t1, t2 = v / a1, v / a2
    tau = min(max(tau, 0.0), T)
    if tau < t1:
        return 0.5 * a1 * tau ** 2, a1 * tau, a1
    if tau <= T - t2:
        return 0.5 * a1 * t1 ** 2 + v * (tau - t1), v, 0.0
    r = T - tau
    return L - 0.5 * a2 * r ** 2, a2 * r, -a2


def trajectory_planner(waypoints, max_iter, waypoint_times, sample_rate, modes, gravity=9.80665,
                       accel_limits=None):
    """Return the (15 x max_iter) desired state matrix.

    accel_limits: optional (accel_limit_up, accel_limit_down, accel_limit_horiz);
    pass them so segments that a cubic cannot fly within limits get re-profiled.
    """
    traj = WaypointTrajectory(waypoints, waypoint_times, sample_rate, modes, accel_limits)
    trajectory_planner.last_profiles = list(traj.profiles)
    out = np.zeros((15, max_iter))
    for k in range(max_iter):
        t = traj.wt[0] + k * traj.dt
        pos, vel, acc, yaw, yaw_rate = traj.evaluate(t)
        out[0:3, k] = pos
        out[3:6, k] = vel
        out[12:15, k] = acc
        out[8, k] = yaw
        out[11, k] = yaw_rate
        ax, ay = acc[0], acc[1]
        out[6, k] = (ax * np.sin(yaw) - ay * np.cos(yaw)) / gravity
        out[7, k] = (ax * np.cos(yaw) + ay * np.sin(yaw)) / gravity
    if max_iter > 1:
        out[9, :] = np.gradient(out[6, :], traj.dt)
        out[10, :] = np.gradient(out[7, :], traj.dt)
    return out


def check_accel_limits(traj, accel_up, accel_down, accel_horiz, tol=1e-9):
    """Return dict of peak planned accelerations and whether each limit holds."""
    az = traj[14]
    ah = np.hypot(traj[12], traj[13])
    res = {
        "max_az": float(az.max()), "min_az": float(az.min()), "max_ahoriz": float(ah.max()),
        "up_ok": bool(az.max() <= accel_up + tol),
        "down_ok": bool(az.min() >= -accel_down - tol),
        "horiz_ok": bool(ah.max() <= accel_horiz + tol),
    }
    res["ok"] = res["up_ok"] and res["down_ok"] and res["horiz_ok"]
    return res
