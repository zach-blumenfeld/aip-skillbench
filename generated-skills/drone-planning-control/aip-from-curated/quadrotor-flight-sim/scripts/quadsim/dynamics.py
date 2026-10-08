"""Nonlinear quadrotor equations of motion; 16-element state derivative."""
import numpy as np

# state: 0:3 pos, 3:6 vel, 6:9 [phi, theta, psi], 9:12 [p, q, r], 12:16 motor RPM


def dynamics(params, state, F_actual, M_actual, rpm_motor_dot):
    m, g = params["mass"], params["gravity"]
    phi, theta, psi = state[6], state[7], state[8]
    cphi, sphi, cth, sth, cpsi, spsi = np.cos(phi), np.sin(phi), np.cos(theta), np.sin(theta), np.cos(psi), np.sin(psi)
    a = F_actual / m
    sd = np.zeros(16)
    sd[0:3] = state[3:6]
    sd[3] = a * (cphi * sth * cpsi + sphi * spsi)
    sd[4] = a * (cphi * sth * spsi - sphi * cpsi)
    sd[5] = -g + a * cphi * cth
    sd[6:9] = state[9:12]
    sd[9:12] = np.linalg.solve(params["inertia"], np.asarray(M_actual, float))
    sd[12:16] = rpm_motor_dot
    return sd
