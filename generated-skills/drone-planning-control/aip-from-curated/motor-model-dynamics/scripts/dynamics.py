"""Quadrotor rigid-body dynamics — 16-element state derivative.

State vector layout (shape (16,))
---------------------------------
| Indices | Meaning                          |
|---------|----------------------------------|
|  0:3    | Position [x, y, z]               |
|  3:6    | Velocity [vx, vy, vz]            |
|  6:9    | Euler angles [phi, theta, psi]   |
|  9:12   | Angular velocity [p, q, r]       |
| 12:16   | Motor RPM [w1, w2, w3, w4]       |

Equations of motion
-------------------
Position derivative   = velocity                          (state[3:6])
Velocity derivative   = gravity + (F/m) * R_zyx * e_z
                        with R_zyx the ZYX Euler rotation
                        applied to the body-frame thrust axis:
  vx_dot = (F/m) * ( cos(psi) sin(theta) cos(phi)
                     + sin(psi) sin(phi) )
  vy_dot = (F/m) * ( sin(psi) sin(theta) cos(phi)
                     - cos(psi) sin(phi) )
  vz_dot = -g + (F/m) * cos(theta) * cos(phi)
Euler derivative      = angular velocity                  (state[9:12])
Angular vel deriv     = I^{-1} * M
Motor RPM derivative  = rpm_dot (from motor model)

Pair with `scripts/motor_model.py` to get `F`, `M`, and `rpm_dot`;
pair with `scripts/integrate.py` for one RK45 timestep.
"""

import numpy as np


def dynamics(params, state, F, M, rpm_dot):
    """Compute state derivative (16,) at the current state.

    Parameters
    ----------
    params : dict
        Must include 'mass', 'gravity', and 'inertia' as a (3, 3)
        diagonal numpy array (i.e. np.diag([Ixx, Iyy, Izz])).
    state : np.ndarray, shape (16,)
        Current state in the layout documented above.
    F : float
        Actual total thrust from the motor model (N).
    M : np.ndarray, shape (3,)
        Actual body-frame moment from the motor model (N*m).
    rpm_dot : np.ndarray, shape (4,)
        Per-motor RPM derivative from the motor model.

    Returns
    -------
    state_dot : np.ndarray, shape (16,)
    """
    m = params["mass"]
    g = params["gravity"]
    I = params["inertia"]

    phi = state[6]
    theta = state[7]
    psi = state[8]

    state_dot = np.zeros(16)
    state_dot[0:3] = state[3:6]
    state_dot[3] = (F / m) * (
        np.cos(psi) * np.sin(theta) * np.cos(phi) + np.sin(psi) * np.sin(phi)
    )
    state_dot[4] = (F / m) * (
        np.sin(psi) * np.sin(theta) * np.cos(phi) - np.cos(psi) * np.sin(phi)
    )
    state_dot[5] = -g + (F / m) * np.cos(theta) * np.cos(phi)
    state_dot[6:9] = state[9:12]
    state_dot[9:12] = np.linalg.solve(I, M)
    state_dot[12:16] = rpm_dot
    return state_dot
