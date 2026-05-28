"""Closed-loop simulator.

Runs the cascaded PID against the quadrotor dynamics and motor model for
`planned['max_iter']` steps; returns the (15, max_iter) actual-state matrix
with the same row layout as the planned matrix.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from controller import CascadePID  # noqa: E402
from dynamics import motor_step, step  # noqa: E402


def simulate(planned: dict, params: dict, gains: dict,
             initial_state: np.ndarray | None = None,
             substeps: int = 10) -> dict:
    """Run the cascaded PID against the quadrotor model.

    The controller updates at `dt`; the dynamics + motor are sub-stepped
    `substeps` times per control update for numerical stability of the
    high-bandwidth attitude loop with Euler integration.
    """
    M = planned["matrix"]
    dt = planned["dt"]
    N = planned["max_iter"]
    dt_sim = dt / max(1, substeps)

    ctrl = CascadePID(
        kp_pos=gains["kp_pos"],
        ki_pos=gains["ki_pos"],
        kd_pos=gains["kd_pos"],
        kp_att=gains["kp_att"],
        ki_att=gains["ki_att"],
        kd_att=gains["kd_att"],
        mass=params["mass"],
        g=params["g"],
        yaw_des=0.0,
        tilt_limit_rad=np.deg2rad(params.get("tilt_limit_deg", 30.0)),
    )

    if initial_state is None:
        state = np.zeros(12)
        state[0:3] = M[0:3, 0]
    else:
        state = np.asarray(initial_state, float).copy()

    thrust_actual = params["mass"] * params["g"]
    motor_tau = params["motor_tau"]

    A = np.zeros((15, N), dtype=float)
    accel_world = np.zeros(3)

    for k in range(N):
        # log BEFORE applying step k so column k aligns with planned column k
        A[0:12, k] = state
        A[12:15, k] = accel_world

        ref = M[:, k]
        # Re-evaluate the controller every substep so the perceived control
        # dt matches the integration dt. Holding torque constant across
        # substeps would push kd*dt/I past the explicit-Euler stability bound.
        for _ in range(substeps):
            thrust_cmd, torque_cmd, _ = ctrl.compute(state, ref, dt_sim)
            thrust_actual = motor_step(thrust_actual, thrust_cmd, motor_tau, dt_sim)
            state, accel_world = step(state, thrust_actual, torque_cmd, params, dt_sim)

    return {"matrix": A}
