#!/usr/bin/env python3
"""Minimal 6-DoF quadrotor dynamics with first-order motor model.

State vector (length 12):
    [x, y, z, vx, vy, vz, phi, theta, psi, p, q, r]

Motor model: each motor's thrust follows first-order dynamics toward the
commanded thrust with time constant tau_motor.

Body frame: x forward, y left, z up (ENU). Motor layout assumed X-config:
    rotor 0: front-right (CW or CCW per `motor_dirs[0]`)
    rotor 1: rear-left
    rotor 2: front-left
    rotor 3: rear-right
Spin directions and torque coefficient `kappa` (motor torque per unit
thrust) are taken from the params dict — agent should plug in values
from system_params.yaml.

Integration: fixed-step RK4 at the caller's `dt`.

Usage:
    sim = Quadrotor(params)
    state = sim.reset(initial_state)
    for k in range(N):
        state = sim.step(motor_thrusts_cmd_k, dt)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class QuadParams:
    mass: float                     # kg
    Ixx: float                      # kg m^2
    Iyy: float                      # kg m^2
    Izz: float                      # kg m^2
    arm_length: float               # m (rotor to CG)
    kappa: float                    # N m per N (drag-to-thrust ratio)
    max_thrust_per_motor: float     # N (one rotor)
    tau_motor: float = 0.02         # s (first-order thrust lag)
    g: float = 9.81                 # m/s^2
    motor_dirs: list = field(default_factory=lambda: [1, 1, -1, -1])
    # +1 = CCW (yaw torque positive), -1 = CW. Adjust to match the sim.


def euler_rotmat(phi: float, theta: float, psi: float) -> np.ndarray:
    """ZYX intrinsic rotation: body -> world. Standard aerospace convention."""
    cphi, sphi = np.cos(phi), np.sin(phi)
    cth, sth = np.cos(theta), np.sin(theta)
    cpsi, spsi = np.cos(psi), np.sin(psi)
    return np.array([
        [cth * cpsi,
         sphi * sth * cpsi - cphi * spsi,
         cphi * sth * cpsi + sphi * spsi],
        [cth * spsi,
         sphi * sth * spsi + cphi * cpsi,
         cphi * sth * spsi - sphi * cpsi],
        [-sth, sphi * cth, cphi * cth],
    ])


def euler_rates(phi: float, theta: float, p: float, q: float, r: float):
    """Body angular rates -> Euler-angle rates (ZYX). Singular at theta=±90."""
    tth = np.tan(theta)
    cth = np.cos(theta)
    return np.array([
        p + q * np.sin(phi) * tth + r * np.cos(phi) * tth,
        q * np.cos(phi) - r * np.sin(phi),
        (q * np.sin(phi) + r * np.cos(phi)) / max(abs(cth), 1e-6) * np.sign(cth),
    ])


class Quadrotor:
    def __init__(self, params: QuadParams):
        self.params = params
        self.state = np.zeros(12)
        self.motor_thrust = np.zeros(4)

    def reset(self, state: np.ndarray | None = None,
              motor_thrust: np.ndarray | None = None) -> np.ndarray:
        self.state = np.zeros(12) if state is None else np.asarray(state, dtype=float).copy()
        if motor_thrust is None:
            # Trim: each motor carries m*g/4 in hover.
            hover = self.params.mass * self.params.g / 4.0
            self.motor_thrust = np.full(4, hover)
        else:
            self.motor_thrust = np.asarray(motor_thrust, dtype=float).copy()
        return self.state.copy()

    def _xdot(self, x: np.ndarray, T_motor: np.ndarray) -> np.ndarray:
        p = self.params
        phi, theta, psi = x[6], x[7], x[8]
        wp, wq, wr = x[9], x[10], x[11]

        # Net thrust (body z up)
        T = float(np.sum(T_motor))
        R = euler_rotmat(phi, theta, psi)
        # Body-frame thrust vector is along +z_body; world = R @ [0,0,T]
        acc_world = R @ np.array([0.0, 0.0, T]) / p.mass - np.array([0.0, 0.0, p.g])

        # Body torques from X-config:
        #   tau_x = arm_length * (T0 + T3 - T1 - T2)   (roll)
        #   tau_y = arm_length * (T2 + T3 - T0 - T1)   (pitch)
        #   tau_z = kappa * sum(dir_i * T_i)           (yaw)
        L = p.arm_length
        tau_x = L * (T_motor[0] + T_motor[3] - T_motor[1] - T_motor[2])
        tau_y = L * (T_motor[2] + T_motor[3] - T_motor[0] - T_motor[1])
        tau_z = p.kappa * sum(d * t for d, t in zip(p.motor_dirs, T_motor))

        # Body angular accelerations (rigid body, no gyroscopic coupling)
        pdot = (tau_x + (p.Iyy - p.Izz) * wq * wr) / p.Ixx
        qdot = (tau_y + (p.Izz - p.Ixx) * wp * wr) / p.Iyy
        rdot = (tau_z + (p.Ixx - p.Iyy) * wp * wq) / p.Izz

        ed = euler_rates(phi, theta, wp, wq, wr)

        dx = np.zeros(12)
        dx[0:3] = x[3:6]
        dx[3:6] = acc_world
        dx[6:9] = ed
        dx[9:12] = [pdot, qdot, rdot]
        return dx

    def step(self, motor_cmd: np.ndarray, dt: float) -> np.ndarray:
        """Advance one dt using RK4 on the dynamics and Euler on motor lag."""
        p = self.params
        motor_cmd = np.clip(np.asarray(motor_cmd, dtype=float), 0.0,
                            p.max_thrust_per_motor)
        # First-order motor lag (Euler step is fine inside one control tick)
        alpha = dt / max(p.tau_motor, 1e-6)
        alpha = min(alpha, 1.0)
        self.motor_thrust = self.motor_thrust + alpha * (motor_cmd - self.motor_thrust)

        # RK4 on rigid-body state with motor thrust held constant
        x = self.state
        k1 = self._xdot(x, self.motor_thrust)
        k2 = self._xdot(x + 0.5 * dt * k1, self.motor_thrust)
        k3 = self._xdot(x + 0.5 * dt * k2, self.motor_thrust)
        k4 = self._xdot(x + dt * k3, self.motor_thrust)
        self.state = x + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
        return self.state.copy()

    def world_accel(self) -> np.ndarray:
        """Return current world-frame acceleration (m/s^2). Useful for the
        actual_trajectory row layout 12:15."""
        return self._xdot(self.state, self.motor_thrust)[3:6]
