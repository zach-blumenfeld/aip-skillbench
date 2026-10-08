"""[F, Mx, My, Mz] -> clipped motor RPMs -> first-order lag -> actual force/moments."""
import numpy as np


def prop_matrix(params):
    cT, cQ, d = params["thrust_coefficient"], params["moment_scale"], params["arm_length"]
    return np.array([
        [cT, cT, cT, cT],
        [0.0, d * cT, 0.0, -d * cT],
        [-d * cT, 0.0, d * cT, 0.0],
        [-cQ, cQ, -cQ, cQ],
    ])


def motor_model(F, M, motor_rpm, params):
    """Return (F_actual, M_actual (3,), rpm_dot (4,)) from the CURRENT motor RPMs."""
    A = params.get("_prop_matrix")
    if A is None:
        A = prop_matrix(params)
    rpm_sq = np.linalg.solve(A, np.array([F, M[0], M[1], M[2]], dtype=float))
    rpm_des = np.clip(np.sqrt(np.maximum(rpm_sq, 0.0)), params["rpm_min"], params["rpm_max"])
    motor_rpm = np.asarray(motor_rpm, float)
    rpm_dot = params["motor_constant"] * (rpm_des - motor_rpm)
    fm = A @ (motor_rpm ** 2)
    return float(fm[0]), fm[1:4], rpm_dot
