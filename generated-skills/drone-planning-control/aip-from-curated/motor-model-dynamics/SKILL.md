---
name: motor-model-dynamics
description: Use this skill when simulating quadrotor physical dynamics — mapping desired thrust/moments to individual motor RPMs via a propeller allocation matrix, applying first-order motor lag, and integrating the nonlinear equations of motion (translational and rotational) using RK45.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3, numpy, scipy. Reads system_params.yaml (mass, gravity, inertia, thrust_coefficient, moment_scale, arm_length, motor_constant, rpm_min, rpm_max).
---

```yaml
purpose: >
  Build the physics layer of the quadrotor simulator. Two cooperating
  modules: a motor model that maps desired total thrust F and body
  moment M into per-motor RPMs through an X-frame propeller
  allocation matrix, clips them to the physical RPM envelope, and
  applies a first-order motor lag; and a rigid-body dynamics function
  that returns the 16-element state derivative (position, velocity,
  Euler angles, angular velocity, motor RPM). One RK45 step over each
  control interval — with the motor model's outputs held constant
  across the interval — advances the state. Derived thrust-envelope
  quantities (T_max, T_min, twr, accel_up_max, accel_down_max) come
  out of the same module so upstream trajectory planners can size
  feasible commands.

trigger_when:
  - Implementing the physics layer of a quadrotor simulator.
  - Mapping a desired (F, Mx, My, Mz) command into per-motor RPMs.
  - Applying first-order motor lag to a commanded RPM vector.
  - Integrating quadrotor equations of motion across a control timestep.
  - Computing the physical thrust envelope (T_max, T_min, twr, max upward/downward acceleration) from motor limits.

do_not_use_when:
  - Implementing the outer position loop or trajectory planning (use `position-controller-trajectory-planner`).
  - Implementing the inner attitude loop (use `attitude-controller-planner`).
  - Parsing natural-language flight commands (use `flight-plan-parser`).
  - Computing step-response metrics or plotting trajectories (use `stepinfo-3d`, `plot-quadrotor`).

scope_and_approval: >
  Pure computation. Reads `system_params.yaml`; writes nothing on its
  own. State, forces, and moments are passed in/out as numpy arrays.
  Safe to run without prompting.

steps:
  - name: load-system-params
    description: >
      Load `system_params.yaml` (mass, gravity, inertia,
      thrust_coefficient cT, moment_scale cQ, arm_length d,
      motor_constant km, rpm_min, rpm_max). Convert the `inertia`
      list into a 3x3 diagonal numpy array (`np.diag(inertia)`)
      before handing it downstream — `dynamics(...)` solves against
      this matrix.
    outputs:
      - name: params
        type: object
        description: System-parameters dict with `inertia` as a (3, 3) np.ndarray.

  - name: compute-thrust-envelope
    description: >
      Derive the physical thrust envelope from motor limits before
      planning trajectories. Returns T_max, T_min, thrust-to-weight
      ratio twr, and the maximum upward/downward accelerations the
      drone can produce. These are the same values the position
      planner's acceleration check compares against (or the values
      that justify `accel_limit_up` / `accel_limit_down` in
      system_params.yaml).
    script: scripts/motor_model.py
    depends_on: [load-system-params]
    inputs:
      - name: params
        type: object
    outputs:
      - name: thrust_envelope
        type: object
        description: "{T_max, T_min, twr, accel_up_max, accel_down_max} — all floats."

  - name: motor-step
    description: >
      One motor-model step. Build the 4x4 X-frame allocation matrix
      from cT, cQ, d (rows = [thrust, roll moment, pitch moment, yaw
      moment]; cols = motors 1..4). Solve `P @ rpm_sq = [F, Mx, My,
      Mz]` for desired squared RPMs, clamp negatives to 0 before
      `sqrt`, then clip to `[rpm_min, rpm_max]`. Apply first-order
      motor lag `rpm_dot = km * (rpm_desired - motor_rpm)`. Compute
      the actual force/moment produced by the CURRENT `motor_rpm`
      via `P @ motor_rpm**2` and return `(F_actual, M_actual,
      rpm_dot)`. F_actual / M_actual feed the dynamics function;
      rpm_dot becomes the state[12:16] derivative.
    script: scripts/motor_model.py
    depends_on: [load-system-params]
    inputs:
      - name: F
        type: float
        description: Desired total thrust (N) from the position controller.
      - name: M
        type: object
        description: Desired body-frame moment (3,) from the attitude controller.
      - name: motor_rpm
        type: object
        description: Current per-motor RPM (4,), i.e. state[12:16].
      - name: params
        type: object
    outputs:
      - name: F_actual
        type: float
      - name: M_actual
        type: object
        description: Body-frame moment (3,) produced by the current motor RPMs.
      - name: rpm_dot
        type: object
        description: Per-motor RPM derivative (4,) — feeds state[12:16] derivative.

  - name: dynamics-step
    description: >
      Compute the 16-element `state_dot` from the current state and
      the (F_actual, M_actual, rpm_dot) from the motor model.
      Position derivative is current velocity (`state[3:6]`). Velocity
      derivative is gravity plus thrust projected into the world frame
      via the ZYX Euler rotation: x and y accelerations depend on
      F/m and sin/cos of all three Euler angles; z acceleration is
      `-g + (F/m) cos(phi) cos(theta)`. Euler-angle derivative is
      current angular velocity (`state[9:12]`). Angular-velocity
      derivative is `I^{-1} M` (solve the inertia matrix against the
      moment vector). Motor-RPM derivative is `rpm_dot` from the
      motor model.
    script: scripts/dynamics.py
    depends_on: [motor-step]
    inputs:
      - name: params
        type: object
      - name: state
        type: object
        description: 16-element state vector (see purpose / scripts/dynamics.py docstring for layout).
      - name: F_actual
        type: float
      - name: M_actual
        type: object
      - name: rpm_dot
        type: object
    outputs:
      - name: state_dot
        type: object
        description: 16-element state derivative.

  - name: integrate-step
    description: >
      Advance the state across one control interval `[t_k, t_{k+1}]`
      using `scipy.integrate.solve_ivp` with `method='RK45'`. The
      motor-model outputs `(F_actual, M_actual, rpm_dot)` are
      computed once at `t_k` and held CONSTANT across the interval
      (zero-order hold) — the ODE RHS sees only the state. Take the
      last column of `sol.y` as the new state. The wrapper is
      intentionally thin so the integration method is one clear
      knob if the simulation later needs a fixed-step scheme.
    script: scripts/integrate.py
    depends_on: [dynamics-step]
    inputs:
      - name: params
        type: object
      - name: state
        type: object
      - name: F_actual
        type: float
      - name: M_actual
        type: object
      - name: rpm_dot
        type: object
      - name: t_k
        type: float
      - name: t_kp1
        type: float
    outputs:
      - name: new_state
        type: object
        description: 16-element state at `t_kp1`.

modes:
  - name: per-timestep
    body: >
      Inside the simulation loop, run `motor-step` -> `integrate-step`
      every control timestep. `dynamics-step` is invoked indirectly
      by the integrator and does not need to be called separately.
      `load-system-params` and `compute-thrust-envelope` run once
      before the loop.
  - name: envelope-only
    body: >
      Run `load-system-params` -> `compute-thrust-envelope` alone to
      derive the physical acceleration limits a trajectory planner
      must respect. No state integration is performed.

scenarios:
  - need: Sizing `accel_limit_up`, `accel_limit_down`, and `accel_limit_horiz` for a new airframe before any trajectory planning.
    context: The trajectory planner's acceleration check needs a feasible envelope, and these limits are direct functions of motor limits and mass.
    action: Run `compute-thrust-envelope` and use `accel_up_max = (T_max - mg)/m` as `accel_limit_up`, `accel_down_max = (mg - T_min)/m` as `accel_limit_down`, and `sqrt(T_max**2 - (mg)**2)/m` as `accel_limit_horiz`. For the bundled 0.77 kg drone this yields ~6.962, ~9.429, and ~13.602 m/s^2 respectively.
    outcome: The planner's `check-acceleration-limits` step now compares against values that match what the physics layer can actually produce.
  - need: A commanded `(F, Mx, My, Mz)` would require a motor to spin at 25000 RPM — outside the envelope.
    context: The propeller allocation solve returns a rpm_desired vector with one element above `rpm_max`.
    action: "`motor-step` clips each per-motor RPM to `[rpm_min, rpm_max]` AFTER `sqrt`. The clipped target then drives the first-order lag, so the simulated motors never violate the envelope."
    outcome: F_actual and M_actual reflect what the physically constrained motors actually produce, not the unbounded request.
  - need: The propeller allocation solve produces a negative `rpm_sq` element because the requested moment is infeasible given the requested thrust.
    context: A naive `sqrt` would produce NaN and propagate through the simulator.
    action: "`motor-step` applies `np.maximum(rpm_sq, 0.0)` before `sqrt`, then clips to the RPM envelope — the offending motor parks at `rpm_min`."
    outcome: Integration continues; the resulting tracking error is the agent's signal that the trajectory or controller gains are pushing the motors out of envelope.

integrations:
  - partner: position-controller-trajectory-planner
    body: >
      Consumes the position controller's `F` (total thrust) as the
      motor model's desired thrust. Produces the thrust envelope
      that bounds the planner's feasible trajectories.
  - partner: attitude-controller-planner
    body: >
      Consumes the attitude controller's `M` (body moment) as the
      motor model's desired moment. The dynamics' angular-velocity
      derivative is `I^{-1} M_actual`, which the attitude controller
      closes the loop on.
  - partner: stepinfo-3d / plot-quadrotor
    body: >
      Consume the actual-state trajectory produced by stepping
      `motor-step` -> `integrate-step` across the simulation horizon
      to compute metrics and write plots.

anti_patterns:
  - Hardcoding the allocation matrix as fixed numbers. Build it from `cT`, `cQ`, and `d` in `params` so a parameter change (different arm length, different propeller) does not silently desynchronize the simulator from the airframe.
  - Taking `sqrt` before clamping the allocation solve. Negative `rpm_sq` entries arise whenever a requested moment cannot be produced at the requested thrust; clamp to 0 first, then `sqrt`, then clip to `[rpm_min, rpm_max]`.
  - Clipping the squared RPMs to `[rpm_min**2, rpm_max**2]` before `sqrt`. Always clip the post-`sqrt` RPMs to `[rpm_min, rpm_max]` — clipping before `sqrt` against squared bounds reads as a bug to anyone reviewing the motor envelope.
  - Forgetting that motors are always spinning. `rpm_min = 3000` is the floor, not zero — the allocator must clip to it, otherwise the first-order lag has to drag the motors up from a stop every step and the dynamics diverge from the real airframe.
  - Computing `F_actual` / `M_actual` from the DESIRED RPMs. Use `P @ motor_rpm**2` where `motor_rpm` is the CURRENT state, not the post-clip desired RPMs — the whole point of the first-order lag is that the produced force/moment trails the command.
  - Updating the motor-model outputs mid-step. `F_actual`, `M_actual`, and `rpm_dot` are held constant across `[t_k, t_{k+1}]` (zero-order hold). Recomputing them inside `solve_ivp`'s RHS breaks the contract and slows the integration without improving fidelity at the control rate.
  - Passing `inertia` as a length-3 list. The dynamics function solves `I^{-1} M` via `np.linalg.solve(I, M)` — `I` must be a (3, 3) array. Wrap with `np.diag(inertia)` once in `load-system-params`.
  - Using `solve_ivp`'s default method or omitting it. The skill specifies RK45 explicitly to keep step behavior consistent across runs and across the agent's environment.
```
