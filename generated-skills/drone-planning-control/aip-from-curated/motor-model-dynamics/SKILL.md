---
name: motor-model-dynamics
description: Use this skill when simulating quadrotor physical dynamics — mapping desired thrust/moments to individual motor RPMs via a propeller allocation matrix, applying first-order motor lag, and integrating the nonlinear equations of motion (translational and rotational) using RK45.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Simulate quadrotor physical dynamics. Map desired [F, Mx, My, Mz] to
  individual motor RPMs through a 4x4 propeller allocation matrix, apply
  first-order motor lag, and integrate the 16-state nonlinear equations of
  motion (translational + rotational + motor RPM) using RK45. Two modules
  form the physics layer: a motor model (commands -> actual thrust/moments)
  and dynamics (forces/moments -> state derivative for ODE integration).

trigger_when:
  - Simulating quadrotor physical dynamics from desired [F, Mx, My, Mz] commands.
  - Mapping commanded thrust and moments to individual motor RPMs for an X-frame quadrotor.
  - Applying first-order motor lag between desired and actual motor speed.
  - Integrating the nonlinear rigid-body equations of motion for a multirotor.
  - Computing maximum thrust, thrust-to-weight ratio, or upward/downward acceleration limits from motor specs.

steps:
  - name: build-allocation-matrix
    description: |
      Build the 4x4 propeller allocation matrix for an X-frame quadrotor with
      arm length d, thrust coefficient cT, and torque coefficient cQ. The
      matrix maps [F, Mx, My, Mz] to squared motor RPMs:

      ```
               motor:  1      2      3      4
      Thrust:         +cT    +cT    +cT    +cT
      Roll  (Mx):      0    +d*cT    0    -d*cT
      Pitch (My):    -d*cT    0    +d*cT    0
      Yaw   (Mz):    -cQ    +cQ    -cQ    +cQ
      ```

  - name: solve-desired-rpms
    description: >
      Solve `prop_matrix @ rpm_sq = [F, Mx, My, Mz]` for `rpm_sq` (desired
      squared RPMs). Clamp negatives to 0, take elementwise sqrt, then clip
      to `[rpm_min, rpm_max]` to honor motor saturation limits.

  - name: apply-motor-lag
    description: >
      Apply first-order motor lag: `rpm_dot = km * (rpm_desired - rpm_current)`
      with `km = motor_constant = 36.5 s^-1` (time constant tau = 1/km ~= 27 ms).
      `rpm_current` lives in state indices 12:16; `rpm_dot` is the motor-RPM
      component of the state derivative.

  - name: compute-actual-force-moment
    description: >
      Compute the realized force/moment from the current motor RPMs using
      `prop_matrix @ (motor_rpm ** 2)`. Return `(F_actual, M_actual, rpm_dot)`.
      F_actual and M_actual are what actually act on the rigid body — they
      differ from the commanded values because of clipping and lag.

  - name: assemble-state-derivative
    description: |
      Compute the 16-element `state_dot` from the current state and the
      applied F_actual, M_actual.

      State vector (length 16):

      | Indices | Meaning |
      |---|---|
      | 0:3   | Position [x, y, z] |
      | 3:6   | Velocity [vx, vy, vz] |
      | 6:9   | Euler angles [phi, theta, psi] |
      | 9:12  | Angular velocity [p, q, r] |
      | 12:16 | Motor RPM [w1, w2, w3, w4] |

      Components of `state_dot`:
      - Position derivative = current velocity (`state[3:6]`).
      - Velocity derivative = gravity + thrust projected into the world frame
        via ZYX Euler rotation. The x/y accelerations depend on `F/m` and on
        sin/cos of all three Euler angles. The z acceleration is
        `-g + (F/m) * cos(phi) * cos(theta)`.
      - Euler angle derivative = current angular velocity (`state[9:12]`).
      - Angular velocity derivative = `I^-1 M` (solve the inertia matrix
        against the moment vector).
      - Motor RPM derivative = `rpm_motor_dot` from the motor model.

  - name: rk45-integration
    description: >
      Integrate one timestep with `scipy.integrate.solve_ivp(method='RK45')`
      over `[t_k, t_{k+1}]`. The ODE function wraps
      `dynamics(params, s, F_actual, M_actual, rpm_motor_dot)` with
      `F_actual` and `M_actual` held constant across the step. After
      solving, take `sol.y[:, -1]` as the new state.

decisions:
  - signal: Solved `rpm_sq` contains negative entries.
    action: Clamp negatives to 0 before taking sqrt. Negative squared RPMs are infeasible; motors cannot spin backward.
  - signal: Desired RPM falls below `rpm_min` or exceeds `rpm_max`.
    action: Clip to `[rpm_min, rpm_max]`. Motors are always spinning (`rpm_min = 3000`) and cannot exceed `rpm_max = 20000`; the commanded allocation is infeasible at the boundary, so use the clipped value and let the downstream `F_actual`/`M_actual` reflect the saturation.
  - signal: Need a per-step constant force/moment for the ODE solver.
    action: Hold `F_actual` and `M_actual` constant across `[t_k, t_{k+1}]`. Recompute them at the next step boundary, not inside the RK45 integrator.

search_shortcuts:
  - category: Motor physical limits
    body: |
      | Parameter | Value | Meaning |
      |---|---|---|
      | `rpm_min`         | 3000        | Minimum motor speed (motors always spinning) |
      | `rpm_max`         | 20000       | Maximum motor speed |
      | `motor_constant` km | 36.5 s^-1 | First-order time constant; tau = 1/km ~= 27 ms |

  - category: Max thrust and acceleration formulas
    body: |
      Derived from the motor limits and the airframe parameters:

      - `T_max = 4 * cT * rpm_max**2`           # all 4 motors at max RPM
      - `T_min = 4 * cT * rpm_min**2`           # all 4 motors at min RPM
      - `twr   = T_max / (mass * gravity)`      # thrust-to-weight ratio
      - max upward acceleration   = `(T_max - mass * g) / mass`
      - max downward acceleration = `(mass * g - T_min) / mass`

anti_patterns:
  - Taking sqrt of `rpm_sq` without first clamping negatives to 0 — produces NaNs whenever the desired allocation is infeasible.
  - Skipping the `[rpm_min, rpm_max]` clip — desired RPMs from the allocation step can exceed motor limits and will silently produce non-physical thrust.
  - Using commanded `[F, Mx, My, Mz]` directly in the dynamics step. The dynamics must use `F_actual` and `M_actual` after clipping and lag, not the raw command.
  - Recomputing `F_actual` / `M_actual` inside the RK45 ODE function. They are held constant across each timestep `[t_k, t_{k+1}]`.
  - Forgetting that the velocity-derivative z component is `-g + (F/m) * cos(phi) * cos(theta)`, not just `F/m - g` — the projection through the Euler rotation matters even in near-hover.
```
