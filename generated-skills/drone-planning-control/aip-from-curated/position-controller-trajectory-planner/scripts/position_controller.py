"""PID position controller for the quadrotor outer loop.

Closes the loop on position and velocity errors. Returns the
total thrust `F` to send into the motor model and the desired
acceleration vector to feed into the attitude planner.

Control law (per timestep)
--------------------------
  pos_err     = current.pos - desired.pos
  vel_err     = current.vel - desired.vel
  integral_e += pos_err * dt
  acc         = desired.acc - kp * pos_err - ki * integral_e - kd * vel_err
  F           = mass * (gravity + acc[2])

The integral term is stateful across calls. ALWAYS create it with
`make_position_integral()` before the loop and pass it explicitly —
never use a mutable default.
"""

import numpy as np


def make_position_integral():
    """Fresh integral-error state for the position controller.

    Returns a dict with a 3-vector under key 'e'. Allocating per
    simulation run prevents accidental cross-run state leakage
    that would otherwise occur with a mutable default argument.
    """
    return {"e": np.zeros(3)}


def position_controller(
    current_state,
    desired_state,
    params,
    integral,
    kp_pos=np.array([30.0, 30.0, 40.0]),
    ki_pos=np.array([0.1, 0.1, 0.5]),
    kd_pos=np.array([10.0, 10.0, 14.0]),
):
    """One PID step on position/velocity errors.

    Parameters
    ----------
    current_state : object with .pos (3,) and .vel (3,) attributes
        Drone's current position and velocity (e.g. SimpleNamespace).
    desired_state : object with .pos (3,), .vel (3,), .acc (3,)
        Trajectory-planner output for this timestep.
    params : dict
        System parameters (must include 'mass', 'gravity', 'sample_rate').
    integral : dict
        Mutable integral-error accumulator from make_position_integral().
    kp_pos, ki_pos, kd_pos : np.ndarray, shape (3,)
        Per-axis PID gains. Defaults are tuned for the 0.77 kg quadrotor
        defined in system_params.yaml; agents tuning for a different
        system MUST override them.

    Returns
    -------
    F : float
        Total thrust command (Newtons).
    acc : np.ndarray, shape (3,)
        Desired acceleration vector to hand to the attitude planner.
    """
    dt = 1.0 / params["sample_rate"]
    pos_err = current_state.pos - desired_state.pos
    vel_err = current_state.vel - desired_state.vel
    integral["e"] += pos_err * dt
    acc = (
        desired_state.acc
        - kp_pos * pos_err
        - ki_pos * integral["e"]
        - kd_pos * vel_err
    )
    F = params["mass"] * (params["gravity"] + acc[2])
    return F, acc
