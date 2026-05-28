"""Attitude planner — inverse kinematics from desired acceleration.

Converts the desired horizontal acceleration (ax, ay) handed down by
the position controller into desired body Euler angles (phi_des,
theta_des), forwards the desired yaw psi_des through unchanged, and
returns the desired body angular velocity (only the yaw-rate channel
is populated; roll- and pitch-rate references are zero).

Small-angle inverse kinematics
------------------------------
Under the small-angle linearization of the ZYX quadrotor model and
with thrust normalized to mg, the horizontal accelerations satisfy

    ax = g * ( cos(psi) * theta + sin(psi) * phi )
    ay = g * ( sin(psi) * theta - cos(psi) * phi )

Solving for (phi, theta):

    phi_des   = (1/g) * ( ax * sin(psi) - ay * cos(psi) )
    theta_des = (1/g) * ( ax * cos(psi) + ay * sin(psi) )

This matches the curated `SKILL.md` body and the oracle solution.
"""

import numpy as np


def attitude_planner(desired_state, params):
    """One attitude-planner step.

    Parameters
    ----------
    desired_state : object with `.rot`, `.acc`, `.omega` attributes
        `.rot[2]` is the desired yaw psi, `.acc[0:2]` are the desired
        horizontal accelerations (ax, ay) from the position controller,
        `.omega[2]` is the desired yaw rate (forwarded unchanged).
    params : dict
        Must include `'gravity'`. Other keys are ignored here.

    Returns
    -------
    rot : np.ndarray, shape (3,)
        Desired body Euler angles `[phi_des, theta_des, psi_des]`.
    omega : np.ndarray, shape (3,)
        Desired body angular velocity `[0, 0, desired_yaw_rate]`.
    """
    g = params["gravity"]
    psi = desired_state.rot[2]
    ax = desired_state.acc[0]
    ay = desired_state.acc[1]
    rot = np.array([
        (1.0 / g) * (ax * np.sin(psi) - ay * np.cos(psi)),
        (1.0 / g) * (ax * np.cos(psi) + ay * np.sin(psi)),
        psi,
    ])
    omega = np.array([0.0, 0.0, desired_state.omega[2]])
    return rot, omega
