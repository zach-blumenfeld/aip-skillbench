#!/usr/bin/env python3
"""Cascade PID controller: outer position loop + inner attitude loop.

Outer loop (position):
    pos_err = pos_des - pos
    vel_err = vel_des - vel
    a_cmd_world = a_des + kp_pos*pos_err + ki_pos*int(pos_err) + kd_pos*vel_err
    a_cmd_world.z += g                        # gravity feed-forward
    thrust_total = m * |a_cmd_world| (clipped)
    From the desired thrust direction and a fixed psi_des (default 0),
    derive desired roll/pitch:
        phi_des   =  arcsin( (a_cmd.x*sin(psi) - a_cmd.y*cos(psi)) / |a_cmd| )
        theta_des =  arctan( (a_cmd.x*cos(psi) + a_cmd.y*sin(psi)) / a_cmd.z )

Inner loop (attitude):
    att_err = att_des - att
    rate_err = rate_des - rate     (rate_des typically 0)
    tau = kp_att*att_err + ki_att*int(att_err) + kd_att*rate_err

Mixer (X-config, matches quadrotor_dynamics.py):
    T0 = T/4 + tau_x/(4L) - tau_y/(4L) + tau_z/(4*kappa)
    T1 = T/4 - tau_x/(4L) - tau_y/(4L) - tau_z/(4*kappa)
    T2 = T/4 - tau_x/(4L) + tau_y/(4L) + tau_z/(4*kappa)
    T3 = T/4 + tau_x/(4L) + tau_y/(4L) - tau_z/(4*kappa)
(adjust kappa sign if your sim defines motor_dirs differently)

Gains are per-axis 3-vectors so tune_gains.py can search each axis.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class PIDGains:
    kp_pos: np.ndarray = field(default_factory=lambda: np.array([4.0, 4.0, 8.0]))
    ki_pos: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 0.0]))
    kd_pos: np.ndarray = field(default_factory=lambda: np.array([3.0, 3.0, 5.0]))
    kp_att: np.ndarray = field(default_factory=lambda: np.array([200.0, 200.0, 80.0]))
    ki_att: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 0.0]))
    kd_att: np.ndarray = field(default_factory=lambda: np.array([20.0, 20.0, 10.0]))


class CascadePID:
    def __init__(self, gains: PIDGains, mass: float, g: float,
                 arm_length: float, kappa: float,
                 max_thrust_per_motor: float,
                 psi_des: float = 0.0,
                 max_tilt_rad: float = np.deg2rad(30.0)):
        self.g = gains
        self.mass = mass
        self.gravity = g
        self.L = arm_length
        self.kappa = kappa
        self.t_max = max_thrust_per_motor
        self.psi_des = psi_des
        self.max_tilt = max_tilt_rad
        self.int_pos = np.zeros(3)
        self.int_att = np.zeros(3)

    def reset(self):
        self.int_pos[:] = 0.0
        self.int_att[:] = 0.0

    def step(self, desired: np.ndarray, actual_state: np.ndarray, dt: float):
        """One control tick.

        desired      : (15,) — slice from planned trajectory at this k
        actual_state : (12,) — current sim state

        Returns motor thrust commands shape (4,), plus desired
        attitude tuple (for logging into rows 6:9 of planned trajectory
        if you want — most evaluators leave those zero in the plan).
        """
        pos_des = desired[0:3]
        vel_des = desired[3:6]
        att_des_raw = desired[6:9]    # usually zero; pilot may set psi
        acc_des = desired[12:15]

        pos = actual_state[0:3]
        vel = actual_state[3:6]
        att = actual_state[6:9]
        rate = actual_state[9:12]

        pos_err = pos_des - pos
        vel_err = vel_des - vel
        self.int_pos += pos_err * dt

        a_cmd = (
            acc_des
            + self.g.kp_pos * pos_err
            + self.g.ki_pos * self.int_pos
            + self.g.kd_pos * vel_err
        )
        # Gravity feed-forward
        a_cmd_z = a_cmd[2] + self.gravity
        a_cmd = np.array([a_cmd[0], a_cmd[1], a_cmd_z])

        # Required thrust magnitude (project onto current body z-axis would
        # be slightly more accurate, but |a_cmd| is robust at small tilt).
        T_total = self.mass * np.linalg.norm(a_cmd)
        T_total = float(np.clip(T_total, 0.0, 4.0 * self.t_max))

        # Desired attitude from a_cmd
        psi = self.psi_des if att_des_raw[2] == 0.0 else att_des_raw[2]
        norm = max(np.linalg.norm(a_cmd), 1e-6)
        phi_des = np.arcsin(
            np.clip((a_cmd[0] * np.sin(psi) - a_cmd[1] * np.cos(psi)) / norm,
                    -1.0, 1.0)
        )
        theta_des = np.arctan2(
            a_cmd[0] * np.cos(psi) + a_cmd[1] * np.sin(psi),
            max(a_cmd[2], 1e-6),
        )
        # Tilt clipping for safety
        phi_des = float(np.clip(phi_des, -self.max_tilt, self.max_tilt))
        theta_des = float(np.clip(theta_des, -self.max_tilt, self.max_tilt))
        att_des = np.array([phi_des, theta_des, psi])

        att_err = att_des - att
        # Wrap yaw error
        att_err[2] = (att_err[2] + np.pi) % (2 * np.pi) - np.pi
        rate_err = -rate     # rate_des assumed 0
        self.int_att += att_err * dt
        tau = (
            self.g.kp_att * att_err
            + self.g.ki_att * self.int_att
            + self.g.kd_att * rate_err
        )

        # Mixer (X-config — matches quadrotor_dynamics.py layout)
        Lq = self.L
        kq = max(self.kappa, 1e-6)
        T0 = T_total / 4 + tau[0] / (4 * Lq) - tau[1] / (4 * Lq) + tau[2] / (4 * kq)
        T1 = T_total / 4 - tau[0] / (4 * Lq) - tau[1] / (4 * Lq) - tau[2] / (4 * kq)
        T2 = T_total / 4 - tau[0] / (4 * Lq) + tau[1] / (4 * Lq) + tau[2] / (4 * kq)
        T3 = T_total / 4 + tau[0] / (4 * Lq) + tau[1] / (4 * Lq) - tau[2] / (4 * kq)
        motors = np.clip(np.array([T0, T1, T2, T3]), 0.0, self.t_max)
        return motors, att_des
