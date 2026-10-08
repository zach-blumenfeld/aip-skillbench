"""Desired acceleration + yaw -> desired roll/pitch (small-angle inverse kinematics)."""
import numpy as np


def attitude_planner(desired_state, params, desired_yaw_rate=0.0):
    ax, ay = float(desired_state.acc[0]), float(desired_state.acc[1])
    psi = float(desired_state.rot[2])
    g = params["gravity"]
    phi_des = (ax * np.sin(psi) - ay * np.cos(psi)) / g
    theta_des = (ax * np.cos(psi) + ay * np.sin(psi)) / g
    return np.array([phi_des, theta_des, psi]), np.array([0.0, 0.0, desired_yaw_rate])
