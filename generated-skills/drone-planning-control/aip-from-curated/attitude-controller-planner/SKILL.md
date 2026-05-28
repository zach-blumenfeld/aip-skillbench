---
name: attitude-controller-planner
description: Use this skill when implementing the inner control loop for a quadrotor — attitude (roll/pitch/yaw) PID control and attitude planning (converting desired acceleration to desired Euler angles). Covers gain layout, integral reset pattern, and the attitude planner inverse kinematics.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3, numpy. Reads system_params.yaml (gravity, sample_rate, inertia).
---

```yaml
purpose: >
  Build the quadrotor inner loop. Two cooperating modules: an attitude
  planner that turns the position controller's desired horizontal
  acceleration (ax, ay) plus the desired yaw psi into desired body
  Euler angles (phi_des, theta_des, psi_des) and a desired angular
  velocity vector [0, 0, desired_yaw_rate]; and a PID attitude
  controller that closes the loop on Euler-angle and angular-velocity
  errors and returns the body moment M = [M_phi, M_theta, M_psi] handed
  to the motor model. Gains are length-3 per-axis arrays multiplied
  element-wise against the error vector BEFORE the inertia matrix
  multiply. The integral accumulator must be allocated per run via
  `make_attitude_integral()`, never via a mutable default — sharing it
  across runs causes x/y oscillation during nominally z-only
  maneuvers.

trigger_when:
  - Implementing the inner loop of a quadrotor (attitude planning + attitude PID control).
  - Converting a desired horizontal acceleration (ax, ay) plus desired yaw into desired roll/pitch.
  - Computing the body moment M handed to the motor model.
  - Tuning attitude-PID gains to remove roll/pitch oscillation or yaw drift while keeping x/y steady.
  - Diagnosing x/y oscillation during a z-only hover or takeoff (almost always attitude integral wind-up).

do_not_use_when:
  - Implementing the outer position loop or trajectory planning (use the sibling skill `position-controller-trajectory-planner`).
  - Implementing the motor allocation / first-order motor lag / rigid-body dynamics (use `motor-model-dynamics`).
  - Parsing natural-language flight commands (use `flight-plan-parser`).
  - Computing step-response metrics or plotting trajectories (use `stepinfo-3d`, `plot-quadrotor`).

scope_and_approval: >
  Pure computation. Reads `system_params.yaml` (specifically `gravity`,
  `sample_rate`, and `inertia` — the latter as a (3, 3) np.ndarray
  built once via `np.diag(inertia_list)`). Writes nothing on its own;
  state, gains, and the integral accumulator are passed in/out as
  numpy arrays and a small mutable dict. Safe to run without
  prompting.

steps:
  - name: gather-inputs
    description: >
      Read `dt = 1.0 / params['sample_rate']` from `system_params.yaml`
      — never hardcode `0.005`. Confirm `params['inertia']` is a
      (3, 3) np.ndarray (built via `np.diag(inertia_list)` when the
      yaml is loaded). Confirm gain arrays are length-3 numpy arrays
      ordered `[phi, theta, psi]`.
    inputs:
      - name: params
        type: object
        description: Loaded system_params.yaml (gravity, sample_rate, inertia, ...).
    outputs:
      - name: dt
        type: float
        description: Control timestep `1.0 / sample_rate`.
      - name: inertia_matrix
        type: object
        description: (3, 3) np.ndarray diagonal inertia matrix.

  - name: attitude-planner-step
    description: >
      Call `attitude_planner(desired_state, params)` to invert the
      small-angle quadrotor kinematics. Given desired horizontal
      acceleration `ax = desired_state.acc[0]`, `ay =
      desired_state.acc[1]`, current desired yaw `psi =
      desired_state.rot[2]`, and `g = params['gravity']`, compute:
      `phi_des   = (1/g) * (ax * sin(psi) - ay * cos(psi))`,
      `theta_des = (1/g) * (ax * cos(psi) + ay * sin(psi))`.
      Return `rot = [phi_des, theta_des, psi]` and
      `omega = [0, 0, desired_state.omega[2]]`. The desired yaw and
      yaw rate are forwarded through unchanged — roll/pitch references
      come from the position-controller's acceleration; the yaw
      reference comes from the trajectory planner.
    script: scripts/attitude_planner.py
    depends_on: [gather-inputs]
    inputs:
      - name: desired_state
        type: object
        description: SimpleNamespace-like; .rot (3,), .acc (3,), .omega (3,) populated by the position controller and trajectory planner.
      - name: params
        type: object
    outputs:
      - name: desired_rot
        type: object
        description: 3-vector `[phi_des, theta_des, psi_des]` — assigned back onto `desired_state.rot` before the controller step.
      - name: desired_omega
        type: object
        description: 3-vector `[0, 0, desired_yaw_rate]` — assigned back onto `desired_state.omega`.

  - name: init-attitude-integral
    description: >
      Call `make_attitude_integral()` ONCE before the simulation loop
      to allocate a fresh `{"e": zeros(3)}` accumulator. Pass it
      explicitly into every `attitude_controller(...)` call. NEVER
      use a mutable default argument — a default dict is shared
      across runs and leaks integral wind-up from prior runs, which
      surfaces as x/y oscillation during nominally z-only maneuvers.
    script: scripts/attitude_controller.py
    depends_on: [gather-inputs]
    outputs:
      - name: integral_state
        type: object
        description: Mutable dict with key `'e'` holding a zeros(3) accumulator.

  - name: attitude-control-step
    description: >
      Inside the simulation loop, call `attitude_controller(current,
      desired, params, integral, kp_att=..., ki_att=..., kd_att=...)`
      to get back the body moment `M`. Internally it computes
      `e = desired.rot - current.rot` (element-wise, length 3),
      `integral["e"] += e * dt`, and
      `M = I @ (kp_att * e + ki_att * integral["e"] + kd_att *
      (desired.omega - current.omega))`. Gains are length-3 per-axis
      arrays multiplied ELEMENT-WISE against the error vectors BEFORE
      the inertia matrix multiply — not via matrix multiply. Feed
      `M` into the motor model alongside the position-controller's
      thrust `F`.
    script: scripts/attitude_controller.py
    depends_on: [init-attitude-integral, attitude-planner-step]
    inputs:
      - name: current_state
        type: object
        description: SimpleNamespace-like; .rot (3,), .omega (3,) for this timestep.
      - name: desired_state
        type: object
        description: SimpleNamespace-like with .rot, .omega populated by the attitude planner.
      - name: params
        type: object
      - name: integral_state
        type: object
      - name: kp_att
        type: object
        description: Length-3 per-axis proportional gains `[phi, theta, psi]`.
      - name: ki_att
        type: object
        description: Length-3 per-axis integral gains — keep <= 0.5 to avoid x/y oscillation.
      - name: kd_att
        type: object
        description: Length-3 per-axis derivative gains.
    outputs:
      - name: moment
        type: object
        description: Body-frame moment `M = [M_phi, M_theta, M_psi]` (3,) handed to the motor model.

  - name: tune-gains
    description: >
      No tuning range is fixed — choose gains freely to satisfy the
      success criteria (per-timestep position error < 0.05 m,
      overshoot < 5%, steady-state error < 0.05 m). Start small
      (e.g. `kp_att = [100, 100, 50]`, `ki_att = [0, 0, 0]`,
      `kd_att = [0, 0, 0]`) and raise gradually. `scripts/attitude_controller.py`
      defaults (`kp_att = [400, 400, 200]`, `ki_att = [0.5, 0.5, 0.5]`,
      `kd_att = [40, 40, 28]`) are a known-good landing point for
      the bundled 0.77 kg airframe. Symptom -> fix table:
      slow roll/pitch correction -> increase kp_att[0] or kp_att[1];
      roll/pitch oscillation -> increase kd_att[0] or kd_att[1];
      yaw drifts slowly -> increase ki_att[2];
      x/y oscillation during hover -> decrease ki_att (any axis).
      Keep `ki_att <= 0.5` on every axis. Record whatever gains you
      land on in `/root/results/<label>/tuning_results.json` under
      the `kp_att`, `ki_att`, `kd_att` keys.
    depends_on: [attitude-control-step]

modes:
  - name: planner-only
    body: >
      Run `gather-inputs` -> `attitude-planner-step` alone. Useful
      when prototyping the inverse-kinematics expression against a
      synthetic (ax, ay, psi) sweep without spinning up the full
      simulator.
  - name: full-loop
    body: >
      Run all steps. `gather-inputs` and `init-attitude-integral`
      execute once before the simulation loop; `attitude-planner-step`
      and `attitude-control-step` execute every timestep. `tune-gains`
      wraps the whole run — adjust gains between runs, never inside
      the loop.

scenarios:
  - need: A 'takeoff to 5 m height in 2 seconds' command shows small but persistent x/y oscillation in the actual trajectory even though the command is z-only.
    context: Attitude integral wind-up — the integral accumulator is shared across runs (mutable default) or `ki_att[0:2]` is too aggressive — produces phantom roll/pitch references that drive horizontal motion.
    action: Allocate `att_integral = make_attitude_integral()` immediately before the per-command simulation loop and pass it into every `attitude_controller(...)` call. If oscillation persists, drop `ki_att[0]` and `ki_att[1]` toward 0 and re-run.
    outcome: x/y stays at the initial (0, 0) through takeoff; per-timestep position error stays under 0.05 m.
  - need: A 'fly from (0,0,3) to (5,0,3) in 2 seconds' command tracks the planned path but with sluggish roll response on the (+x) leg.
    context: Roll proportional gain `kp_att[0]` is too low; the body cannot tilt fast enough to produce the commanded ax inside the segment time.
    action: Raise `kp_att[0]` (and symmetrically `kp_att[1]`) toward the bundled default of 400. If roll begins to oscillate, raise `kd_att[0]`/`kd_att[1]` toward 40 to damp it.
    outcome: Roll tracks the desired phi_des produced by the attitude planner without lag; per-timestep position error stays under 0.05 m through the fly segment.
  - need: A 'hover at 3 m height for 5 seconds' command shows a slow yaw drift away from the desired yaw.
    context: Yaw integral gain `ki_att[2]` is zero; small bias terms or numerical asymmetries accumulate uncorrected.
    action: Raise `ki_att[2]` modestly (e.g. 0 -> 0.5). Keep `ki_att[0]` and `ki_att[1]` small (<= 0.5) so the same change does not induce x/y oscillation.
    outcome: Yaw holds the desired psi through the hover window without inducing horizontal oscillation.

integrations:
  - partner: position-controller-trajectory-planner
    body: >
      The position controller's desired acceleration vector `acc` is
      assigned onto `desired_state.acc` BEFORE `attitude_planner(...)`
      runs each timestep. The attitude planner reads `acc[0]`,
      `acc[1]`, and `desired_state.rot[2]` (the yaw target from the
      trajectory) and writes the desired roll/pitch back. The two
      skills compose end-to-end inside the per-timestep loop:
      `F, ds.acc = position_controller(...)` then
      `ds.rot, ds.omega = attitude_planner(ds, params)` then
      `M = attitude_controller(cs, ds, params, att_integral, ...)`.
  - partner: motor-model-dynamics
    body: >
      The body moment `M` from this skill, together with the total
      thrust `F` from the position controller, are the two inputs the
      motor model converts into per-motor RPMs. The motor model
      writes `state[9:12]` (body angular velocity) and the body
      Euler angles `state[6:9]` over time; those become
      `current_state.omega` and `current_state.rot` on the next
      timestep, closing the inner loop.
  - partner: stepinfo-3d / plot-quadrotor
    body: >
      Consume the actual vs. desired trajectories produced by the
      surrounding simulation loop. Roll/pitch/yaw error plots come
      from the same `desired` (post-planner) and `actual` matrices
      this skill helps populate.

anti_patterns:
  - Using a mutable default argument for the attitude integral. Always call `make_attitude_integral()` before the per-command simulation loop and pass the dict explicitly — a shared default leaks integral wind-up from prior runs and surfaces as x/y oscillation during nominally z-only maneuvers.
  - Letting `ki_att` exceed 0.5 on any axis. Attitude integral wind-up is the dominant cause of x/y oscillation during hover and z-only maneuvers; cap each `ki_att` axis at 0.5 and tune `kp_att` / `kd_att` first.
  - Hardcoding `dt = 0.005`. Always derive `dt = 1.0 / params['sample_rate']` so a `sample_rate` change in `system_params.yaml` propagates correctly.
  - Treating `kp_att`, `ki_att`, `kd_att` as scalars or matrix-multiplying them against the error. The gains are length-3 per-axis arrays multiplied ELEMENT-WISE against the error vector; only the inertia matrix `I` participates in the final `@` (matrix-multiply).
  - Passing the raw `inertia` list into the controller. The controller does `I @ (...)`; `I` must be a (3, 3) np.ndarray. Build it once with `np.diag(inertia_list)` when loading `system_params.yaml`.
  - Forgetting to overwrite `desired_state.rot` and `desired_state.omega` with the attitude-planner outputs before calling `attitude_controller(...)`. The raw `desired_state.rot` from the trajectory matrix has the planner's yaw but no roll/pitch reference; the controller must see the planner's inverted roll/pitch to track the commanded horizontal acceleration.
  - Updating gains inside the per-timestep loop. Pick a tuning per run, record it in `tuning_results.json`, and re-run — mid-run gain changes invalidate the integral accumulator's history.
```
