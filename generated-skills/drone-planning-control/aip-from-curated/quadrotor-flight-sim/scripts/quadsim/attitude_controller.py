"""Inner loop: Euler-angle PID scaled by the inertia matrix -> moments [M1, M2, M3]."""
import numpy as np

DEFAULT_GAINS = {"kp_att": [100.0, 100.0, 50.0], "ki_att": [0.0, 0.0, 0.0], "kd_att": [0.0, 0.0, 0.0]}


def make_attitude_integral():
    """Fresh integral state; create once per simulation run, before the loop."""
    return {"e": np.zeros(3)}


def attitude_controller(current_state, desired_state, params, integral):
    """Gains come from params['kp_att'|'ki_att'|'kd_att'] as [phi, theta, psi] arrays."""
    kp = np.asarray(params.get("kp_att", DEFAULT_GAINS["kp_att"]), float)
    ki = np.asarray(params.get("ki_att", DEFAULT_GAINS["ki_att"]), float)
    kd = np.asarray(params.get("kd_att", DEFAULT_GAINS["kd_att"]), float)
    dt = 1.0 / params["sample_rate"]
    e = np.asarray(desired_state.rot) - np.asarray(current_state.rot)
    integral["e"] = integral["e"] + e * dt
    rate_err = np.asarray(desired_state.omega) - np.asarray(current_state.omega)
    return params["inertia"] @ (kp * e + ki * integral["e"] + kd * rate_err)
