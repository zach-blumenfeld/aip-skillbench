# Quadrotor dynamics & cascaded PID — reference

## State vector

A 12-dim state captures translation and rotation:

```
state = [ x, y, z,        # world position (m)
          vx, vy, vz,     # world velocity (m/s)
          phi, theta, psi,# ZYX Euler angles (rad): roll, pitch, yaw
          p, q, r ]       # body angular rate (rad/s)
```

The output `(15, max_iter)` trajectory adds rows 12:15 = world acceleration.

## Rigid-body dynamics (near-hover, Euler integration)

Translation:
```
F_world = R_eb(phi,theta,psi) · [0, 0, T]ᵀ           # total thrust along body +z
a       = F_world / m  -  [0, 0, g]ᵀ                 # world-frame acceleration
```

Rotation:
```
ω = [p, q, r]ᵀ
ω̇ = I⁻¹ ( τ_body  -  ω × (I·ω) )
```

`I` is the body inertia tensor — `diag(Ixx, Iyy, Izz)` for a symmetric quad.

## First-order motor model

Real rotors don't deliver commanded thrust instantly. Model the actual thrust as
first-order in the commanded thrust with time constant `motor_tau`:

```
T_actual_{k+1} = T_actual_k + (T_cmd_k - T_actual_k) · (dt / motor_tau)
```

Saturate at `T_actual >= 0`. Without this lag the closed-loop sim is
optimistic — gains tuned against an instantaneous-thrust model will overshoot
on a real platform.

## Cascaded PID

### Outer loop: position → desired body z-axis + thrust

```
e_p = p_des - p
e_v = v_des - v
a_des = Kp_pos · e_p + Ki_pos · ∫e_p + Kd_pos · e_v + a_ff + g·ẑ_world
T_cmd  = m · |a_des|
ẑ_b_des = a_des / |a_des|
```

Recover desired roll/pitch from `ẑ_b_des` assuming yaw = yaw_des (0 for this
skill's commands):

```
zx_yaw =  ẑ_b_des.x·cos(ψ_des) + ẑ_b_des.y·sin(ψ_des)
zy_yaw = -ẑ_b_des.x·sin(ψ_des) + ẑ_b_des.y·cos(ψ_des)
theta_des = atan2( zx_yaw, ẑ_b_des.z )
phi_des   = atan2(-zy_yaw, sqrt(zx_yaw² + ẑ_b_des.z²) )
```

Clamp `phi_des, theta_des` to a tilt limit (default 30°) so the inversion
remains well-conditioned.

### Inner loop: attitude → body torques

```
e_att = wrap(att_des - att)
e_ω   = 0 - ω                # implicit rate reference
τ_cmd = Kp_att · e_att + Ki_att · ∫e_att + Kd_att · e_ω
```

`wrap()` keeps each angle error in (-π, π].

## Anti-windup

Clamp `∫e_p` and `∫e_att` componentwise to a fixed magnitude (default ±5.0).
Otherwise short tracking errors during the rise build up integrator gain and
cause the response to overshoot once the disturbance clears.

## Integration

Euler is fine for `dt ≤ 0.01 s` in this regime. If you push to larger steps or
add aggressive maneuvers, switch to RK4 — the scripts isolate the integrator in
`dynamics.step()`.

## Why this matches the task

- The task supplies `accel_limit_*` — they're not used by the dynamics directly,
  but they bound the *planned* trajectory's acceleration so the controller's
  feedforward demand stays achievable.
- Yaw never appears in any of the four command templates → fix `psi_des = 0`.
- The instruction says "drone motor and dynamics" without bounding rotor count;
  modeling at the thrust+torque level (not motor mixing) keeps the skill
  applicable to any rotor topology.
