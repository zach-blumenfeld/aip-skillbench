"""Outer loop: position/velocity PID -> thrust F and desired acceleration."""
import numpy as np

DEFAULT_GAINS = {"kp_pos": [0.1, 0.1, 0.1], "ki_pos": [0.0, 0.0, 0.0], "kd_pos": [0.0, 0.0, 0.0]}


def make_position_integral():
    """Fresh integral state; create once per simulation run, before the loop."""
    return {"e": np.zeros(3)}


def position_controller(current_state, desired_state, params, integral):
    """Gains come from params['kp_pos'|'ki_pos'|'kd_pos'] (3-element arrays, element-wise)."""
    kp = np.asarray(params.get("kp_pos", DEFAULT_GAINS["kp_pos"]), float)
    ki = np.asarray(params.get("ki_pos", DEFAULT_GAINS["ki_pos"]), float)
    kd = np.asarray(params.get("kd_pos", DEFAULT_GAINS["kd_pos"]), float)
    dt = 1.0 / params["sample_rate"]
    pos_err = np.asarray(current_state.pos) - np.asarray(desired_state.pos)
    vel_err = np.asarray(current_state.vel) - np.asarray(desired_state.vel)
    integral["e"] = integral["e"] + pos_err * dt
    acc = np.asarray(desired_state.acc) - kp * pos_err - ki * integral["e"] - kd * vel_err
    F = params["mass"] * (params["gravity"] + acc[2])
    return F, acc
