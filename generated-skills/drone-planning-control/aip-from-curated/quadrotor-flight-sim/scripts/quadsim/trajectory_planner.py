"""Waypoints + modes -> (15 x max_iter) desired state; acceleration-limit checks."""
import numpy as np
from scipy.interpolate import CubicSpline


def _yaw_quat(yaw):
    return np.array([np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2)])


class WaypointTrajectory:
    """Steps one sample per call through a piecewise trajectory.

    Each non-hover segment is a clamped CubicSpline (zero velocity at both ends) over
    [t_start, t_end] for x, y, z and a separate one for yaw; hover segments hold the
    segment's end waypoint with zero velocity/acceleration.
    """

    def __init__(self, waypoints, waypoint_times, sample_rate, modes):
        self.wp = np.asarray(waypoints, dtype=float)
        self.times = np.asarray(waypoint_times, dtype=float)
        self.modes = list(modes)
        if self.wp.shape[0] != 4 or self.wp.shape[1] != len(self.times) or len(self.modes) != len(self.times) - 1:
            raise ValueError("need waypoints (4 x n), times (n,), modes (n-1)")
        self.dt = 1.0 / float(sample_rate)
        self.t_current = float(self.times[0])
        self.segments = []
        for i, mode in enumerate(self.modes):
            t0, t1 = self.times[i], self.times[i + 1]
            if mode == "hover":
                self.segments.append(None)
            else:
                pos = CubicSpline([t0, t1], self.wp[0:3, i:i + 2].T, bc_type="clamped")
                yaw = CubicSpline([t0, t1], self.wp[3, i:i + 2], bc_type="clamped")
                self.segments.append((pos, yaw))

    def evaluate(self, t):
        """Return (pos, quaternion, vel, acc, yaw) at time t; holds the last waypoint after the end."""
        if t >= self.times[-1]:
            end = self.wp[:, -1]
            return end[0:3].copy(), _yaw_quat(end[3]), np.zeros(3), np.zeros(3), float(end[3])
        i = int(np.clip(np.searchsorted(self.times, t, side="right") - 1, 0, len(self.modes) - 1))
        seg = self.segments[i]
        if seg is None:  # hover: hold this segment's end waypoint
            end = self.wp[:, i + 1]
            return end[0:3].copy(), _yaw_quat(end[3]), np.zeros(3), np.zeros(3), float(end[3])
        pos_s, yaw_s = seg
        yaw = float(yaw_s(t))
        return pos_s(t), _yaw_quat(yaw), pos_s(t, 1), pos_s(t, 2), yaw

    def __call__(self):
        pos, quat, vel, acc, _ = self.evaluate(self.t_current)
        self.t_current += self.dt
        return pos, quat, vel, acc, np.zeros(3)


def trajectory_planner(waypoints, max_iter, waypoint_times, sample_rate, modes):
    """Return trajectory_state (15 x max_iter): rows 0:3 pos, 3:6 vel, 6:9 [phi, theta, psi]
    (roll/pitch 0; the attitude planner fills them during simulation), 9:12 ang vel, 12:15 acc."""
    traj = WaypointTrajectory(waypoints, waypoint_times, sample_rate, modes)
    out = np.zeros((15, int(max_iter)))
    for k in range(int(max_iter)):
        pos, _, vel, acc, yaw = traj.evaluate(traj.t_current)
        traj.t_current += traj.dt
        out[0:3, k], out[3:6, k], out[8, k], out[12:15, k] = pos, vel, yaw, acc
    return out


def max_iter_for(waypoint_times, sample_rate):
    """Samples covering t0..time_final inclusive; time_final = waypoint_times[-1]."""
    duration = float(waypoint_times[-1] - waypoint_times[0])
    return int(round(duration * float(sample_rate))) + 1


def check_accel_limits(trajectory_state, params, tol=1e-9):
    """Peak planned accelerations vs. the physical limits. Returns a dict with `ok`."""
    a = trajectory_state[12:15]
    up, down, horiz = float(a[2].max(initial=0)), float(a[2].min(initial=0)), float(np.hypot(a[0], a[1]).max(initial=0))
    lim = {k: params[k] for k in ("accel_limit_up", "accel_limit_down", "accel_limit_horiz")}
    viol = []
    if up > lim["accel_limit_up"] + tol:
        viol.append(f"az up {up:.3f} > {lim['accel_limit_up']:.3f}")
    if down < -lim["accel_limit_down"] - tol:
        viol.append(f"az down {down:.3f} < -{lim['accel_limit_down']:.3f}")
    if horiz > lim["accel_limit_horiz"] + tol:
        viol.append(f"horizontal {horiz:.3f} > {lim['accel_limit_horiz']:.3f}")
    return {"ok": not viol, "peak_up": up, "peak_down": down, "peak_horiz": horiz, "violations": viol}


def min_feasible_duration(start, end, params, margin=1.05):
    """Shortest clamped-cubic duration whose peak accel (6*delta/T^2) stays within limits."""
    d = np.asarray(end, float)[:3] - np.asarray(start, float)[:3]
    dz, dxy = abs(d[2]), float(np.hypot(d[0], d[1]))
    need = max(dz / params["accel_limit_up"], dz / params["accel_limit_down"], dxy / params["accel_limit_horiz"])
    return float(np.sqrt(6.0 * need) * margin)


def stretch_to_limits(waypoints, waypoint_times, modes, params):
    """Lengthen any non-hover segment that would exceed the limits. Returns (new_times, changes)."""
    times = np.asarray(waypoint_times, float).copy()
    changes = []
    shift = 0.0
    new = times.copy()
    for i, mode in enumerate(modes):
        T = times[i + 1] - times[i]
        if mode != "hover":
            T_min = min_feasible_duration(waypoints[:, i], waypoints[:, i + 1], params)
            if T < T_min:
                changes.append({"segment": i, "mode": mode, "from_s": float(T), "to_s": T_min})
                shift += T_min - T
        new[i + 1] = times[i + 1] + shift
    return new, changes
