"""One simulation timestep — integrate the dynamics with RK45.

`F_actual`, `M_actual`, and `rpm_dot` come from `motor_model(...)` at
the start of the step and are held CONSTANT across `[t_k, t_{k+1}]`
(zero-order hold). The dynamics RHS therefore depends only on the
state. We hand it to `scipy.integrate.solve_ivp(method='RK45')` over
the timestep interval and return the final-column state as the new
state vector.

This wrapper is intentionally thin so the integration method is one
clear knob — swap RK45 for a fixed-step scheme here if the simulation
needs to run cheaper without touching the rest of the skill.
"""

import numpy as np
from scipy.integrate import solve_ivp

from dynamics import dynamics


def integrate_step(params, state, F_actual, M_actual, rpm_dot, t_k, t_kp1):
    """Advance the 16-element state from `t_k` to `t_kp1`.

    The forces, moments, and rpm derivatives are held constant across
    the interval (zero-order hold from the start-of-step motor model).

    Parameters
    ----------
    params : dict
        Passed through to `dynamics(...)` (needs mass, gravity, inertia).
    state : np.ndarray, shape (16,)
        Current state at `t_k`.
    F_actual : float
        Net thrust from motor_model at `t_k`.
    M_actual : np.ndarray, shape (3,)
        Body-frame moment from motor_model at `t_k`.
    rpm_dot : np.ndarray, shape (4,)
        Per-motor RPM derivative from motor_model at `t_k`.
    t_k, t_kp1 : float
        Step start and end times (s).

    Returns
    -------
    new_state : np.ndarray, shape (16,)
        State at `t_kp1`.
    """

    def ode(_t, s):
        return dynamics(params, s, F_actual, M_actual, rpm_dot)

    sol = solve_ivp(ode, (t_k, t_kp1), state, method="RK45")
    return sol.y[:, -1]
