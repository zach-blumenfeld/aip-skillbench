"""Quadrotor motor model — propeller allocation and first-order lag.

Maps a desired total thrust `F` and body-frame moment vector
`M = [Mx, My, Mz]` to per-motor RPMs via the X-frame propeller
allocation matrix, applies the first-order motor lag, and returns
the actual thrust/moments produced by the current motor RPMs plus
the per-motor RPM derivatives the dynamics integrator consumes.

X-frame allocation matrix (motor indices 1..4)
----------------------------------------------
            motor 1   motor 2   motor 3   motor 4
Thrust:      +cT       +cT       +cT       +cT
Roll  Mx:     0       +d cT      0        -d cT
Pitch My:   -d cT      0       +d cT       0
Yaw   Mz:   -cQ       +cQ       -cQ       +cQ

where `cT = thrust_coefficient`, `cQ = moment_scale`, `d = arm_length`.

Step sequence
-------------
1. Build the 4x4 prop matrix from `cT`, `cQ`, `d`.
2. Solve  prop_matrix @ rpm_sq = [F, Mx, My, Mz]  for desired squared RPMs.
3. Clamp negatives to 0, take sqrt, then clip to [rpm_min, rpm_max].
4. Apply first-order motor lag:  rpm_dot = km * (rpm_desired - rpm_current).
5. Compute actual force/moment from the current `motor_rpm` via
   `prop_matrix @ motor_rpm**2`.

Returns
-------
F_actual : float          Net thrust (N) from current motor RPMs.
M_actual : np.ndarray (3,) Body-frame moment [Mx, My, Mz] (N*m).
rpm_dot  : np.ndarray (4,) Per-motor RPM derivative (RPM/s) for the
                          dynamics integrator (state[12:16] derivative).
"""

import numpy as np


def build_prop_matrix(params):
    """4x4 X-frame propeller allocation matrix.

    Rows: [thrust, roll moment, pitch moment, yaw moment].
    Cols: motors 1..4. Multiplied by `rpm**2` yields the produced
    [F, Mx, My, Mz] vector.
    """
    cT = params["thrust_coefficient"]
    cQ = params["moment_scale"]
    d = params["arm_length"]
    return np.array(
        [
            [cT, cT, cT, cT],
            [0.0, d * cT, 0.0, -d * cT],
            [-d * cT, 0.0, d * cT, 0.0],
            [-cQ, cQ, -cQ, cQ],
        ]
    )


def motor_model(F, M, motor_rpm, params):
    """One motor-model step.

    Parameters
    ----------
    F : float
        Desired total thrust (N) from the position controller.
    M : np.ndarray, shape (3,)
        Desired body-frame moment [Mx, My, Mz] (N*m) from the
        attitude controller.
    motor_rpm : np.ndarray, shape (4,)
        Current per-motor RPMs from the state vector (state[12:16]).
    params : dict
        System parameters; must include thrust_coefficient,
        moment_scale, arm_length, motor_constant, rpm_min, rpm_max.

    Returns
    -------
    F_actual : float
    M_actual : np.ndarray, shape (3,)
    rpm_dot  : np.ndarray, shape (4,)
    """
    P = build_prop_matrix(params)
    km = params["motor_constant"]
    rpm_min = params["rpm_min"]
    rpm_max = params["rpm_max"]

    target = np.array([F, M[0], M[1], M[2]], dtype=float)
    rpm_sq_desired = np.linalg.solve(P, target)
    # Negative squared RPMs are physically impossible — clamp before sqrt.
    rpm_desired = np.sqrt(np.maximum(rpm_sq_desired, 0.0))
    rpm_desired = np.clip(rpm_desired, rpm_min, rpm_max)

    rpm_dot = km * (rpm_desired - np.asarray(motor_rpm, dtype=float))

    actual = P @ (np.asarray(motor_rpm, dtype=float) ** 2)
    F_actual = float(actual[0])
    M_actual = actual[1:4]
    return F_actual, M_actual, rpm_dot


def thrust_envelope(params):
    """Derived motor-limit quantities used to size feasible trajectories.

    Returns a dict with:
      T_max            : N        4 * cT * rpm_max**2
      T_min            : N        4 * cT * rpm_min**2
      twr              : -        T_max / (mass * gravity)
      accel_up_max     : m/s^2    (T_max - m g) / m
      accel_down_max   : m/s^2    (m g - T_min) / m   (magnitude of max
                                  downward accel; positive number)
    """
    cT = params["thrust_coefficient"]
    rpm_max = params["rpm_max"]
    rpm_min = params["rpm_min"]
    mass = params["mass"]
    g = params["gravity"]

    T_max = 4.0 * cT * rpm_max ** 2
    T_min = 4.0 * cT * rpm_min ** 2
    twr = T_max / (mass * g)
    accel_up_max = (T_max - mass * g) / mass
    accel_down_max = (mass * g - T_min) / mass
    return {
        "T_max": T_max,
        "T_min": T_min,
        "twr": twr,
        "accel_up_max": accel_up_max,
        "accel_down_max": accel_down_max,
    }
