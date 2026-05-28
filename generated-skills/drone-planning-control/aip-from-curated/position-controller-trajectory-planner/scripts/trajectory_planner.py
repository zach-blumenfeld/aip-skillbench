"""Trajectory planner for quadrotor outer-loop control.

Converts a sequence of waypoints + per-segment modes into a
`(15 × max_iter)` desired-state matrix. Row layout matches the
simulation state used by the position controller and downstream
attitude/motor pipeline:

  rows  0:3  position    [x,  y,  z]
  rows  3:6  velocity    [vx, vy, vz]
  rows  6:9  orientation [phi, theta, psi]   (yaw at row 8)
  rows  9:12 angular vel [p,  q,  r]
  rows 12:15 acceleration [ax, ay, az]

Segment modes
-------------
  'hover'   : constant position, zero velocity and acceleration
  'takeoff' : cubic spline from ground to target height
  'fly'     : cubic spline from start position to end position
  'land'    : cubic spline from current height to ground

Implementation notes
--------------------
`WaypointTrajectory` is a callable that steps through a per-segment
cubic spline one sample at a time. A clamped boundary condition
(zero velocity at both endpoints) keeps the planned trajectory in
sync with the drone's initial rest state and avoids the large
initial-velocity mismatch that would otherwise push per-timestep
position error above the success threshold.
"""

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.spatial.transform import Rotation


class WaypointTrajectory:
    """Steps through a per-segment cubic spline one sample at a time.

    On each call, returns (pos, quaternion, vel, acc, omega) and
    advances the internal time pointer by `dt = 1/sample_rate`.

    Parameters
    ----------
    waypoints : array-like, shape (n_points, n_dims)
        XYZ coordinates of the segment endpoints. For per-segment
        use, `n_points == 2`.
    waypoint_times : array-like, length n_points
        Absolute arrival times for each waypoint.
    sample_rate : float
        Control-loop rate in Hz; sets `dt = 1.0 / sample_rate`.
    """

    def __init__(self, waypoints, waypoint_times, sample_rate):
        self.dt = 1.0 / sample_rate
        self.t_current = float(waypoint_times[0])
        wps = np.asarray(waypoints, dtype=float)
        n_dims = wps.shape[1] if wps.ndim > 1 else 1
        bc = (1, np.zeros(n_dims))
        self.cs = CubicSpline(
            np.asarray(waypoint_times, dtype=float), wps, bc_type=(bc, bc)
        )

    def __call__(self):
        t = self.t_current
        pos = self.cs(t)
        vel = self.cs(t, 1)
        acc = self.cs(t, 2)
        self.t_current += self.dt
        return pos, np.array([1.0, 0.0, 0.0, 0.0]), vel, acc, np.zeros(3)


def quat2eul(q):
    """Identity-quaternion → zero Euler angles (XYZ convention)."""
    return Rotation.from_quat([q[1], q[2], q[3], q[0]]).as_euler("XYZ")


def trajectory_planner(waypoints, max_iter, waypoint_times, sample_rate, modes):
    """Build the (15 × max_iter) desired-state matrix.

    Parameters
    ----------
    waypoints : np.ndarray, shape (4, n_points)
        Stacked [x; y; z; yaw] columns. `n_points = len(modes) + 1`.
    max_iter : int
        Total number of timesteps to fill. Typically
        `ceil(waypoint_times[-1] * sample_rate) + 1`.
    waypoint_times : array-like, length n_points
        Absolute arrival times at each waypoint, starting at 0.
    sample_rate : int | float
        Hz; controls dt and index → time mapping.
    modes : list[str]
        One mode per segment: 'hover', 'takeoff', 'fly', or 'land'.

    Returns
    -------
    np.ndarray, shape (15, max_iter)
        Desired state per timestep. After the final waypoint time,
        the trajectory holds the final position with zero vel/acc.
    """
    ts = np.zeros((15, int(max_iter)))
    t0 = float(waypoint_times[0])

    for seg, mode in enumerate(modes):
        t_s = float(waypoint_times[seg])
        t_e = float(waypoint_times[seg + 1])
        i_s = int(round((t_s - t0) * sample_rate))
        i_e = min(int(round((t_e - t0) * sample_rate)), int(max_iter))
        if i_e - i_s <= 0:
            continue

        wp_s = waypoints[:, seg]
        wp_e = waypoints[:, seg + 1]

        if mode == "hover":
            ts[0:3, i_s:i_e] = wp_s[0:3, None]
            ts[8, i_s:i_e] = wp_s[3]
            continue

        traj = WaypointTrajectory(
            np.stack([wp_s[0:3], wp_e[0:3]]),
            [t_s, t_e],
            sample_rate,
        )
        yaw_cs = CubicSpline([t_s, t_e], [wp_s[3], wp_e[3]])
        for i in range(i_s, i_e):
            pos, ori, vel, acc, omg = traj()
            ts[0:3, i] = pos
            ts[3:6, i] = vel
            ts[6:9, i] = quat2eul(ori)
            ts[8, i] = float(yaw_cs(t0 + i / sample_rate))
            ts[9:12, i] = omg
            ts[12:15, i] = acc

    i_last = int(round((waypoint_times[-1] - t0) * sample_rate))
    for i in range(i_last, int(max_iter)):
        ts[0:3, i] = waypoints[0:3, -1]
        ts[8, i] = waypoints[3, -1]

    return ts
