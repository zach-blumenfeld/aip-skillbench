"""Quadrotor 6-DOF rigid-body dynamics with first-order motor lag.

State (12): [x, y, z, vx, vy, vz, phi, theta, psi, p, q, r]
Controls:   total thrust T (N, along body +z), body torques tau (3,)
Motor:      thrust_actual evolves first-order toward thrust_cmd, tau=motor_tau.

Integration is Euler at the controller dt. Sufficient for dt <= 0.01 s near
hover; if you push to larger steps, switch to RK4.
"""
from __future__ import annotations

import numpy as np


def Reb(phi: float, theta: float, psi: float) -> np.ndarray:
    """Body-to-world rotation, ZYX Euler convention."""
    cp, sp = np.cos(phi), np.sin(phi)
    ct, st = np.cos(theta), np.sin(theta)
    cy, sy = np.cos(psi), np.sin(psi)
    return np.array(
        [
            [cy * ct, cy * st * sp - sy * cp, cy * st * cp + sy * sp],
            [sy * ct, sy * st * sp + cy * cp, sy * st * cp - cy * sp],
            [-st,     ct * sp,                 ct * cp],
        ]
    )


def step(state: np.ndarray, thrust_actual: float, torque_cmd: np.ndarray,
         params: dict, dt: float) -> tuple[np.ndarray, np.ndarray]:
    """One Euler step. Returns (next_state, world_acceleration)."""
    p = state[0:3]
    v = state[3:6]
    e = state[6:9]
    w = state[9:12]
    m = params["mass"]
    g = params["g"]
    I = np.diag([params["Ixx"], params["Iyy"], params["Izz"]])

    # translation: F_world = R_eb @ [0,0,T] - m g e_z
    f_world = Reb(*e) @ np.array([0.0, 0.0, thrust_actual])
    a = f_world / m - np.array([0.0, 0.0, g])

    # rotation: I wdot = tau - w x (I w)
    wdot = np.linalg.solve(I, torque_cmd - np.cross(w, I @ w))

    # Semi-implicit (symplectic) Euler: update velocities first, then positions
    # with the new velocities. Much more stable than fully explicit Euler for
    # oscillatory systems like attitude under strong PID feedback.
    v2 = v + a * dt
    w2 = w + wdot * dt
    p2 = p + v2 * dt
    e2 = e + w2 * dt  # small-angle Euler-rate ≈ body-rate; valid near hover

    next_state = np.concatenate([p2, v2, e2, w2])
    return next_state, a


def motor_step(thrust_actual: float, thrust_cmd: float, motor_tau: float, dt: float) -> float:
    """First-order lag: T += (T_cmd - T) * (dt/tau). Saturates at T >= 0."""
    nxt = thrust_actual + (thrust_cmd - thrust_actual) * (dt / max(motor_tau, 1e-6))
    return max(nxt, 0.0)
