"""PID attitude controller for the quadrotor inner loop.

Closes the loop on Euler-angle and angular-velocity errors and
returns the body-frame moment M = [M_phi, M_theta, M_psi] that gets
handed to the motor model.

Control law (per timestep)
--------------------------
  e           = desired_rot - current_rot       (element-wise, length 3)
  integral_e += e * dt
  M           = I @ (kp * e + ki * integral_e + kd * (desired_omega - current_omega))

`I` is the (3, 3) inertia matrix (`np.diag(inertia)` from
`system_params.yaml`); gains are length-3 per-axis arrays multiplied
ELEMENT-WISE against the error vector BEFORE the inertia matrix
multiply.

The integral term is stateful across calls. ALWAYS allocate it with
`make_attitude_integral()` before the simulation loop and pass it
explicitly into every `attitude_controller(...)` call — never use a
mutable default argument. Sharing a default dict across runs leaks
integral wind-up from prior runs and causes x/y oscillation during
nominally z-only maneuvers.

Gain defaults
-------------
`(kp_att, ki_att, kd_att) = ([400, 400, 200], [0.5, 0.5, 0.5],
[40, 40, 28])` is a known-good starting point for the bundled 0.77 kg
airframe. The curated `SKILL.md` opens with a more conservative
`kp_att = [100, 100, 50]`, `ki_att = [0, 0, 0]`, `kd_att = [0, 0, 0]`
as a deliberately gentle anchor; raise gradually toward the defaults
here while watching for roll/pitch oscillation. Keep `ki_att` small
(<= 0.5) on every axis — attitude integral wind-up is the dominant
cause of x/y oscillation during z-only maneuvers.
"""

import numpy as np


def make_attitude_integral():
    """Fresh integral-error state for the attitude controller.

    Returns a dict with a 3-vector under key `'e'`. Allocating per
    simulation run prevents the cross-run state leakage that occurs
    with a mutable default argument.
    """
    return {"e": np.zeros(3)}


def attitude_controller(
    current_state,
    desired_state,
    params,
    integral,
    kp_att=np.array([400.0, 400.0, 200.0]),
    ki_att=np.array([0.5, 0.5, 0.5]),
    kd_att=np.array([40.0, 40.0, 28.0]),
):
    """One PID step on Euler-angle and angular-velocity errors.

    Parameters
    ----------
    current_state : object with `.rot` (3,) and `.omega` (3,) attributes
        Drone's current Euler angles and body angular velocity
        (typically a SimpleNamespace built from the simulator state).
    desired_state : object with `.rot` (3,) and `.omega` (3,) attributes
        Output of the attitude planner: desired Euler angles and
        desired body angular velocity for this timestep.
    params : dict
        System parameters. Must include `'sample_rate'` (Hz) and
        `'inertia'` as a (3, 3) np.ndarray (build it with
        `np.diag(inertia_list)` once when loading
        `system_params.yaml`).
    integral : dict
        Mutable integral-error accumulator from
        `make_attitude_integral()`.
    kp_att, ki_att, kd_att : np.ndarray, shape (3,)
        Per-axis PID gains (defaults tuned for the 0.77 kg quadrotor;
        override for a different airframe).

    Returns
    -------
    M : np.ndarray, shape (3,)
        Body-frame moment `[M_phi, M_theta, M_psi]` handed to the
        motor model.
    """
    dt = 1.0 / params["sample_rate"]
    I = params["inertia"]
    e = desired_state.rot - current_state.rot
    integral["e"] += e * dt
    return I @ (
        kp_att * e
        + ki_att * integral["e"]
        + kd_att * (desired_state.omega - current_state.omega)
    )
