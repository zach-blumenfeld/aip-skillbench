---
name: attitude-controller-planner
description: Use this skill when implementing the inner control loop for a quadrotor — attitude (roll/pitch/yaw) PID control and attitude planning (converting desired acceleration to desired Euler angles). Covers gain layout, integral reset pattern, and the attitude planner inverse kinematics.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Implement the quadrotor inner control loop as two cooperating modules: an
  attitude planner that converts desired linear acceleration into desired
  roll/pitch angles (inverse kinematics), and an attitude controller that runs
  PID feedback on Euler-angle errors and emits body-frame moments
  [M1, M2, M3]. Encodes the gain layout, the per-run integral reset pattern,
  and the planner's inverse-kinematics formulas.

trigger_when:
  - Writing or modifying the inner (attitude) control loop for a quadrotor simulation.
  - Implementing `attitude_planner` (desired acceleration → desired roll/pitch).
  - Implementing `attitude_controller` (PID on Euler-angle errors → moments).
  - Tuning attitude PID gains (kp_att, ki_att, kd_att).
  - Debugging x/y oscillations during hover, slow roll/pitch correction, or yaw drift.

steps:
  - name: attitude-planner
    description: >
      Given desired acceleration [ax, ay] and current yaw psi, compute desired
      roll/pitch via inverse kinematics. phi_des is proportional to
      (ax*sin(psi) - ay*cos(psi)) / g; theta_des is proportional to
      (ax*cos(psi) + ay*sin(psi)) / g. Return rot = [phi_des, theta_des, psi]
      and omega = [0, 0, desired_yaw_rate].
  - name: init-integral
    description: >
      Before the simulation loop, call `make_attitude_integral()` to create a
      fresh `{"e": zeros(3)}` dict. Never use a mutable default argument for
      this state — it causes wind-up across simulation runs. Pass the integral
      explicitly into `attitude_controller` on every iteration.
  - name: attitude-controller
    description: >
      PID control on Euler-angle errors scaled by the inertia matrix.
      (1) Compute angle error: e = desired_rot - current_rot (element-wise, 3D vector).
      (2) Accumulate integral: integral_e += e * dt, where dt = 1.0 / params['sample_rate']
      (never hardcode 0.005).
      (3) Compute moment: M = I @ (kp * e + ki * integral_e + kd * (desired_omega - current_omega)).
      Gains are arrays [phi, theta, psi]; multiply element-wise with the error, not matrix
      multiply, before applying the inertia `@`.
  - name: tune-gains
    description: >
      No tuning range is prescribed — choose PID gains freely to best satisfy
      the success criteria. Start small (e.g. kp_att = [100, 100, 50],
      ki_att = [0.0, 0.0, 0.0], kd_att = [0.0, 0.0, 0.0]) and increase
      gradually. Keep ki small (<= 0.5 for attitude) to avoid integral
      wind-up that manifests as x/y oscillation during z-only maneuvers.
      Use the `decisions` table below to map observed symptoms to gain edits.

decisions:
  - signal: Slow roll/pitch correction.
    action: Increase kp_att[0] or kp_att[1].
  - signal: Roll/pitch oscillates.
    action: Increase kd_att[0] or kd_att[1].
  - signal: Yaw drifts slowly.
    action: Increase ki_att[2].
  - signal: x/y oscillation during hover.
    action: Decrease ki_att (attitude integral wind-up is the usual cause).

scenarios:
  - need: Wire the planner and controller into the main simulation loop.
    action: |
      Create the integral state once before the loop, then call planner +
      controller every iteration, passing the integral by reference:

          att_integral = make_attitude_integral()   # once before the loop

          for iter_ in range(max_iter - 1):
              ...
              desired_state.rot, desired_state.omega = attitude_planner(desired_state, params)
              M = attitude_controller(current_state, desired_state, params, att_integral)
    outcome: >
      Integral accumulates across iterations within a run but is freshly
      zero at the start of every run, eliminating cross-run wind-up.

anti_patterns:
  - Using a mutable default argument for the attitude integral — causes wind-up across simulation runs. Always pass `integral` explicitly and create it with `make_attitude_integral()` before the loop.
  - Setting ki_att too large (> 0.5) — attitude integral wind-up shows up as x/y oscillations during z-only maneuvers.
  - Hardcoding `dt = 0.005` instead of computing `dt = 1.0 / params['sample_rate']`.
  - Treating gain arrays `[phi, theta, psi]` as matrices — they must multiply element-wise with the error before the inertia `@`.
```
