# 6-DoF Quadrotor Dynamics — quick reference

State (12-D): `[x, y, z, vx, vy, vz, phi, theta, psi, p, q, r]`.

Euler convention: ZYX intrinsic, body→world rotation matrix
```
R(phi, theta, psi) =
[ cth*cpsi,  sphi*sth*cpsi - cphi*spsi,  cphi*sth*cpsi + sphi*spsi ]
[ cth*spsi,  sphi*sth*spsi + cphi*cpsi,  cphi*sth*spsi - sphi*cpsi ]
[    -sth,                  sphi*cth,                  cphi*cth   ]
```

## Equations of motion
```
m * a_world = R * [0, 0, T_total]  -  [0, 0, m*g]

I_b * omega_dot + omega x (I_b * omega) = tau_body
```

With diagonal inertia tensor `diag(Ixx, Iyy, Izz)`:
```
p_dot = (tau_x + (Iyy - Izz) * q * r) / Ixx
q_dot = (tau_y + (Izz - Ixx) * p * r) / Iyy
r_dot = (tau_z + (Ixx - Iyy) * p * q) / Izz
```

Body rates → Euler rates (ZYX):
```
phi_dot   = p + q*sin(phi)*tan(theta) + r*cos(phi)*tan(theta)
theta_dot = q*cos(phi) - r*sin(phi)
psi_dot   = (q*sin(phi) + r*cos(phi)) / cos(theta)
```
Singular at `theta = ±90°` — keep `max_tilt < 60°` in the controller.

## Motor model
First-order lag with time constant `tau_motor`:
```
T_i(t+dt) = T_i(t) + (dt / tau_motor) * (T_cmd_i - T_i(t))
```
Saturate `T_cmd_i ∈ [0, max_thrust_per_motor]`.

## X-configuration mixer (consistent with `cascade_pid.py`)
Rotor index map (looking down on the drone, +x forward, +y left):
```
        T0 (FR, +)        T2 (FL, -)
            \             /
             \           /
              +---------+
              |   CG    |
              +---------+
             /           \
            /             \
        T3 (RR, -)        T1 (RL, +)
```
where sign denotes CCW (+) / CW (-) rotation:
```
tau_x = L * (T0 + T3 - T1 - T2)   # roll, body x
tau_y = L * (T2 + T3 - T0 - T1)   # pitch, body y
tau_z = kappa * (T0 + T1 - T2 - T3)
T_total = T0 + T1 + T2 + T3
```
Inverse (mixer in the controller):
```
T0 = T/4 + tau_x/(4L) - tau_y/(4L) + tau_z/(4*kappa)
T1 = T/4 - tau_x/(4L) - tau_y/(4L) - tau_z/(4*kappa)
T2 = T/4 - tau_x/(4L) + tau_y/(4L) + tau_z/(4*kappa)
T3 = T/4 + tau_x/(4L) + tau_y/(4L) - tau_z/(4*kappa)
```

If `system_params.yaml` ships a different rotor numbering or spin
pattern, **fix the mixer constants in `cascade_pid.py` and the matching
torque equations in `quadrotor_dynamics.py` simultaneously** — they must
agree or the inner loop will drive away from the setpoint.

## Common pitfalls
- Forgetting gravity in `acc_world` — drone falls.
- Using world-frame thrust instead of body-frame — vehicle yaws but
  doesn't translate.
- Mismatched motor sign convention between dynamics and mixer — yaw
  torque sign flips, controller becomes unstable.
- Euler-integrating rigid-body state at dt > 5 ms — high-frequency
  attitude oscillation looks like instability but is integrator error;
  switch to RK4.
