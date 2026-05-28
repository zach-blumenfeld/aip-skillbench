"""Cascaded PID controller.

Outer loop (position):
    a_des = kp_pos * (p_des - p) + ki_pos * int(e_p) + kd_pos * (v_des - v) + a_ff + [0,0,g]
    thrust_cmd = m * ||a_des||
    z_b_des    = a_des / ||a_des||
    From z_b_des and yaw_des, recover desired (phi_des, theta_des), clamp to tilt limit.

Inner loop (attitude):
    e_att      = wrap(att_des - att)
    tau_cmd    = kp_att * e_att + ki_att * int(e_att) + kd_att * (0 - w)

Integral terms are anti-windup-clamped to a fixed magnitude.
"""
from __future__ import annotations

import numpy as np

_INT_CLAMP = 5.0


def _wrap(a: float) -> float:
    return float(np.arctan2(np.sin(a), np.cos(a)))


class CascadePID:
    def __init__(self, kp_pos, ki_pos, kd_pos, kp_att, ki_att, kd_att,
                 mass: float, g: float, yaw_des: float = 0.0,
                 tilt_limit_rad: float = np.deg2rad(30.0)):
        self.kp_pos = np.asarray(kp_pos, float)
        self.ki_pos = np.asarray(ki_pos, float)
        self.kd_pos = np.asarray(kd_pos, float)
        self.kp_att = np.asarray(kp_att, float)
        self.ki_att = np.asarray(ki_att, float)
        self.kd_att = np.asarray(kd_att, float)
        self.m = mass
        self.g = g
        self.yaw_des = yaw_des
        self.tilt = tilt_limit_rad
        self.int_p = np.zeros(3)
        self.int_a = np.zeros(3)

    def reset(self):
        self.int_p[:] = 0.0
        self.int_a[:] = 0.0

    def compute(self, state: np.ndarray, ref_col: np.ndarray, dt: float):
        """ref_col is the 15-vector planned column at this timestep.
        Returns (thrust_cmd, torque_cmd, att_des).
        """
        p = state[0:3]
        v = state[3:6]
        e = state[6:9]
        w = state[9:12]

        p_des = ref_col[0:3]
        v_des = ref_col[3:6]
        a_ff = ref_col[12:15]

        ep = p_des - p
        ev = v_des - v
        self.int_p = np.clip(self.int_p + ep * dt, -_INT_CLAMP, _INT_CLAMP)

        a_des = (
            self.kp_pos * ep
            + self.ki_pos * self.int_p
            + self.kd_pos * ev
            + a_ff
            + np.array([0.0, 0.0, self.g])
        )

        # thrust along desired body-z direction
        a_norm = float(np.linalg.norm(a_des))
        thrust = self.m * a_norm
        if a_norm < 1e-6:
            zb = np.array([0.0, 0.0, 1.0])
        else:
            zb = a_des / a_norm

        # recover desired roll/pitch from zb assuming yaw = yaw_des
        cy, sy = np.cos(self.yaw_des), np.sin(self.yaw_des)
        # rotated horizontal components in yaw-aligned frame
        zx = zb[0] * cy + zb[1] * sy
        zy = -zb[0] * sy + zb[1] * cy
        theta_des = float(np.arctan2(zx, zb[2]))
        phi_des = float(np.arctan2(-zy, np.sqrt(zx * zx + zb[2] * zb[2])))
        theta_des = float(np.clip(theta_des, -self.tilt, self.tilt))
        phi_des = float(np.clip(phi_des, -self.tilt, self.tilt))
        att_des = np.array([phi_des, theta_des, self.yaw_des])

        # attitude PID
        ea = np.array([
            _wrap(att_des[0] - e[0]),
            _wrap(att_des[1] - e[1]),
            _wrap(att_des[2] - e[2]),
        ])
        self.int_a = np.clip(self.int_a + ea * dt, -_INT_CLAMP, _INT_CLAMP)
        ew = -w  # desired body rate ~ 0 (rate ref handled implicitly via attitude PID)
        torque = self.kp_att * ea + self.ki_att * self.int_a + self.kd_att * ew

        return float(thrust), torque, att_des
