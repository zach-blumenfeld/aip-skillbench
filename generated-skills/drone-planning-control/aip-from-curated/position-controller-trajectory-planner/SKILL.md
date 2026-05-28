---
name: position-controller-trajectory-planner
description: Use this skill when implementing the outer control loop for a quadrotor — position PID control (position/velocity error → thrust and desired acceleration) and trajectory planning from flight-plan waypoints (takeoff, hover, fly, land segments → smooth 15-row state matrix).
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3, numpy, scipy, PyYAML. Reads system_params.yaml from /root/system_params.yaml by default.
---

```yaml
purpose: >
  Build the quadrotor outer loop. Two cooperating modules: a trajectory
  planner that turns a parsed flight plan (waypoints + per-segment modes:
  hover / takeoff / fly / land) into a smooth (15 × max_iter) desired-state
  matrix via cubic splines, and a PID position controller that closes the
  loop on position/velocity errors to produce thrust F and desired
  acceleration. The planned trajectory must stay inside the drone's
  physical acceleration envelope so the motors never saturate; the
  controller's integral term must be allocated per run, never via a
  mutable default. Outputs land under `/root/results/<label>/` so the
  verifier can pick them up.

trigger_when:
  - Implementing the outer loop of a quadrotor (position control + trajectory planning).
  - Converting a parsed flight plan (waypoints, times, modes) into a desired-state matrix.
  - Computing the thrust and desired acceleration to hand to the attitude planner.
  - Tuning position-PID gains to meet per-timestep tracking accuracy and overshoot targets.
  - Verifying that a planned trajectory respects the drone's physical acceleration limits.

do_not_use_when:
  - Implementing the inner attitude loop or motor model (use the sibling skills `attitude-controller-planner`, `motor-model-dynamics`).
  - Parsing raw natural-language flight commands (use `flight-plan-parser`; its output feeds this skill).
  - Computing step-response metrics (use `stepinfo-3d`); plotting trajectories (use `plot-quadrotor`).

scope_and_approval: >
  Writes only inside `/root/results/<label>/` (the per-command output
  folder), specifically `planned_trajectory.npy` and any files the
  surrounding pipeline writes alongside it. Reads `system_params.yaml`.
  No network access, no destructive operations elsewhere on the
  filesystem. Safe to run without prompting.

steps:
  - name: gather-inputs
    description: >
      Read `dt = 1.0 / params['sample_rate']` and `time_final =
      waypoint_times[-1]` from the parsed flight plan and system_params.
      Never hardcode either. Derive `max_iter` from these so the
      trajectory length matches the simulation length.
    inputs:
      - name: params
        type: object
        description: Loaded system_params.yaml (mass, gravity, sample_rate, accel limits, ...).
      - name: waypoints
        type: object
        description: (4, n_points) array of [x; y; z; yaw] columns from flight_plan_parser.
      - name: waypoint_times
        type: object
        description: Length-n_points absolute arrival times, starting at 0.
      - name: modes
        type: object
        description: List of per-segment modes ('hover' | 'takeoff' | 'fly' | 'land').
    outputs:
      - name: sample_rate
        type: float
      - name: dt
        type: float
      - name: max_iter
        type: integer
        description: Number of timesteps the trajectory matrix and simulation will span.

  - name: plan-trajectory
    description: >
      Call `trajectory_planner(waypoints, max_iter, waypoint_times,
      sample_rate, modes)` to build the (15 × max_iter) desired-state
      matrix. Per segment: 'hover' holds position with zero velocity and
      acceleration; the other modes fit a cubic spline (clamped so
      velocity is zero at both endpoints, which keeps the planner in
      sync with the drone's at-rest state and avoids the large
      initial-velocity mismatch that pushes per-timestep error above the
      0.05 m tolerance). Yaw is interpolated by a separate cubic spline
      over `[t_start, t_end]`. Row layout: 0:3 pos, 3:6 vel, 6:9
      orientation (yaw at row 8), 9:12 angular vel, 12:15 acceleration.
      The planner takes only the parsed flight-plan outputs — never a
      `question` string.
    script: scripts/trajectory_planner.py
    depends_on: [gather-inputs]
    inputs:
      - name: waypoints
        type: object
      - name: waypoint_times
        type: object
      - name: modes
        type: object
      - name: sample_rate
        type: float
      - name: max_iter
        type: integer
    outputs:
      - name: trajectory_matrix
        type: object
        description: np.ndarray of shape (15, max_iter); rows 12:15 are the accelerations checked against the physical envelope.

  - name: check-acceleration-limits
    description: >
      Validate the planned trajectory against the drone's physical
      acceleration envelope from `system_params.yaml`. Upward `az ≤
      accel_limit_up` (≈ 6.962 m/s² for the default 0.77 kg drone),
      downward `az ≥ -accel_limit_down` (≈ -9.429 m/s²), and
      `√(ax²+ay²) ≤ accel_limit_horiz` (≈ 13.602 m/s²) at every
      timestep. A violation means the motors would saturate; either
      lengthen the segment time or split it into multiple waypoints
      before proceeding. Numeric thresholds and the iteration over
      timesteps are encoded in the script — do not eyeball the matrix.
    script: scripts/check_acceleration_limits.py
    depends_on: [plan-trajectory]
    inputs:
      - name: trajectory_matrix
        type: object
      - name: params
        type: object
    outputs:
      - name: limits_ok
        type: boolean
      - name: limits_report
        type: object
        description: Per-axis max/min observed accelerations plus any per-timestep violations.

  - name: save-planned-trajectory
    description: >
      For each command file `<label>.txt`, create `/root/results/<label>/`
      and save the planned matrix there as `planned_trajectory.npy`
      immediately after planning. The test suite loads this file to
      verify the acceleration envelope, so the save must happen before
      simulation runs — not after. Other artifacts the surrounding
      pipeline writes to the same folder include `metrics_3d.json`,
      `tuning_results.json`, `actual_trajectory.npy`, and `plots/`.
    depends_on: [check-acceleration-limits]
    inputs:
      - name: trajectory_matrix
        type: object
      - name: label
        type: string
        description: Command identifier (filename without extension, e.g. "001").
    outputs:
      - name: out_dir
        type: string
        description: Per-command output directory, e.g. /root/results/001.
      - name: planned_trajectory_path
        type: string

  - name: init-position-integral
    description: >
      Call `make_position_integral()` before the simulation loop to
      allocate a fresh `{"e": zeros(3)}` accumulator. Allocate once per
      run; pass it explicitly into every `position_controller(...)`
      call. NEVER use a mutable default for this state — sharing it
      across runs causes integral wind-up from previous runs to leak in.
    script: scripts/position_controller.py
    depends_on: [save-planned-trajectory]
    outputs:
      - name: integral_state
        type: object
        description: Mutable dict with key 'e' holding a zeros(3) accumulator.

  - name: position-control-step
    description: >
      Inside the simulation loop, call `position_controller(current,
      desired, params, integral, kp_pos=..., ki_pos=..., kd_pos=...)`
      to get back `(F, acc)`. Internally it computes
      `pos_err = current.pos - desired.pos`,
      `vel_err = current.vel - desired.vel`,
      `integral["e"] += pos_err * dt`,
      `acc = desired.acc - kp*pos_err - ki*integral - kd*vel_err`,
      `F = mass * (gravity + acc[2])`. Feed `acc` into the attitude
      planner; feed `F` into the motor model.
    script: scripts/position_controller.py
    depends_on: [init-position-integral]
    inputs:
      - name: current_state
        type: object
        description: SimpleNamespace-like with .pos, .vel attributes for this timestep.
      - name: desired_state
        type: object
        description: SimpleNamespace-like with .pos, .vel, .acc attributes from the trajectory matrix.
      - name: params
        type: object
      - name: integral_state
        type: object
      - name: kp_pos
        type: object
        description: Length-3 per-axis proportional gains.
      - name: ki_pos
        type: object
      - name: kd_pos
        type: object
    outputs:
      - name: thrust
        type: float
        description: Total thrust F in Newtons, fed into the motor model.
      - name: desired_acceleration
        type: object
        description: 3-vector handed to the attitude planner as desired_state.acc.

  - name: tune-gains
    description: >
      No tuning range is fixed — choose gains freely to satisfy the
      success criteria (per-timestep position error < 0.05 m, overshoot
      < 5%, steady-state error < 0.05 m). Start conservative and raise
      gradually. Symptom → fix table:
      slow altitude response → increase kp_pos[2];
      altitude overshoot → increase kd_pos[2];
      persistent altitude offset → increase ki_pos[2];
      x/y oscillation during hover → decrease ki_pos[0] and ki_pos[1].
      The script defaults
      (kp=[30,30,40], ki=[0.1,0.1,0.5], kd=[10,10,14]) are a known-good
      starting point for the bundled 0.77 kg drone; record whatever
      gains you end up using in `tuning_results.json`.

modes:
  - name: plan-only
    body: >
      Run `gather-inputs` → `plan-trajectory` →
      `check-acceleration-limits` → `save-planned-trajectory`. Useful
      for sweeping segment-time or waypoint choices before committing
      to a full simulation.
  - name: full-loop
    body: >
      Run all steps. The trajectory is planned and saved once per
      command; `init-position-integral` and `position-control-step`
      run inside the per-timestep simulation loop alongside the
      attitude controller and motor model.

scenarios:
  - need: A 'takeoff to 5 m in 2 s' command must reach 5 m without per-timestep error spikes.
    context: Default cubic spline (not clamped) leaves nonzero velocity at t=0 while the drone starts at rest, producing an initial 3 m/s mismatch and per-timestep error > 0.05 m.
    action: The bundled `trajectory_planner` uses a clamped CubicSpline (zero velocity at both endpoints), so the planned start matches the drone's initial state.
    outcome: Per-timestep position error stays under 0.05 m through the whole takeoff.
  - need: A 'fly from (0,0,3) to (5,0,3) in 1 s' command — short horizontal segment.
    context: The peak horizontal acceleration of a clamped cubic between two points is roughly 6 · |Δx| / T². For 5 m in 1 s that's ≈30 m/s², well above `accel_limit_horiz = 13.602 m/s²`.
    action: The check-acceleration-limits step flags the violation. Lengthen the segment time (e.g. 2 s → ≈7.5 m/s², which fits) or split the path into multiple waypoints before re-planning.
    outcome: The replanned trajectory passes the limits check and the motors don't saturate at run time.
  - need: Persistent altitude steady-state error of ~0.04 m on hover.
    action: Bump `ki_pos[2]` (e.g. 0.5 → 0.7). Re-run; if oscillation appears, back off slightly and raise `kd_pos[2]`.
    outcome: Steady-state altitude error drops below the 0.05 m threshold without inducing overshoot.

integrations:
  - partner: flight-plan-parser
    body: >
      Consumes its (waypoints, waypoint_times, modes) output directly.
      `time_final = waypoint_times[-1]`; never hardcode it.
  - partner: attitude-controller-planner
    body: >
      The position controller's `acc` output becomes the attitude
      planner's input. The attitude planner converts it into desired
      roll/pitch and forwards yaw from the desired state.
  - partner: motor-model-dynamics
    body: >
      Thrust `F` from the position controller, combined with the
      attitude controller's moment `M`, feeds the motor model and
      drone dynamics.
  - partner: stepinfo-3d / plot-quadrotor
    body: >
      Consume the actual vs. desired trajectories produced by the
      surrounding simulation loop to write `metrics_3d.json` and the
      `plots/` directory under the same per-command output folder.

anti_patterns:
  - Using a mutable default for the position-controller integral. Always call `make_position_integral()` before the loop and pass the dict explicitly — sharing the dict across runs leaks integral wind-up between commands.
  - Hardcoding `dt` or `time_final`. Read `dt = 1.0 / params['sample_rate']` from `system_params.yaml` and `time_final = waypoint_times[-1]` from the parsed flight plan.
  - Passing the natural-language `question` into `trajectory_planner`. The planner takes only `waypoints`, `max_iter`, `waypoint_times`, `sample_rate`, and `modes` — the flight-plan parser is what consumes the prompt text.
  - Skipping the save of `planned_trajectory.npy` (or saving it after simulation). The verifier loads this file to check the physical acceleration envelope; save it immediately after `trajectory_planner` returns.
  - Eyeballing the acceleration matrix to judge whether limits hold. Run `scripts/check_acceleration_limits.py` (or the equivalent `check_limits` function) — limit values are derived from `system_params.yaml`, not hardcoded.
  - Reusing a single `/root/results/` for every command. Each command writes into `/root/results/<label>/` with its own `planned_trajectory.npy`, `metrics_3d.json`, `tuning_results.json`, `actual_trajectory.npy`, and `plots/`.
  - Cranking `ki_pos[0]` / `ki_pos[1]` during hover tuning. Horizontal integral gain causes x/y oscillation around the hover point; reduce it instead.
```
