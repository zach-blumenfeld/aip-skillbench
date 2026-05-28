---
name: quadrotor-trajectory-control
description: Plan and execute piecewise-continuous quadrotor trajectories from natural-language commands (takeoff, hover, land, fly-to-point), tune a cascade PID controller per command, and emit the exact /root/results/<id>/ bundle (metrics_3d.json, tuning_results.json, planned_trajectory.npy, actual_trajectory.npy, plots/). Use whenever the task requires per-timestep position-error tolerance (~0.05 m), bounded overshoot (<5%), bounded steady-state error (<0.05 m), and respects per-axis acceleration limits read from system_params.yaml. Activates on drone-planning-control and any quadrotor PID/trajectory task with that shape.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.10+, numpy, pyyaml, matplotlib. No network access needed.
---

```yaml
purpose: >
  Solve the drone-planning-control task: ingest natural-language
  commands (takeoff / hover / land / fly), plan smooth quintic
  trajectories that respect per-axis acceleration limits, simulate a
  6-DoF quadrotor with first-order motor dynamics under a cascade
  position+attitude PID controller, tune the gains per command, and emit
  the canonical /root/results/<id>/ output bundle. Encodes the exact
  output schemas, step-response metric definitions, baseline gains,
  cascade structure (outer position -> desired tilt -> inner attitude
  -> motor mixer), and the four numerical success criteria the
  evaluator checks.

trigger_when:
  - Solving the drone-planning-control task or any quadrotor variant
    that ingests NL commands from a `commands/` folder and writes per-
    command results under `/root/results/<id>/`.
  - The environment specifies `accel_limit_up`, `accel_limit_down`,
    `accel_limit_horiz` in `system_params.yaml` and requires the
    planned trajectory to satisfy them at every timestep.
  - The required outputs include `metrics_3d.json`,
    `tuning_results.json`, `(15, max_iter)` `.npy` state matrices, and
    `plots/` with `desired_vs_actual.png`, `errors.png`,
    `cumulative_errors.png`.
  - Per-timestep Euclidean position error must stay below ~0.05 m,
    overshoot below 5%, and steady-state error below 0.05 m.

do_not_use_when:
  - Task is fixed-wing, helicopter, or any non-multirotor aircraft.
  - Task is perception/SLAM/planning-only with no closed-loop control.
  - No `system_params.yaml` and no per-axis acceleration limits are
    given (the planner depends on them).

scope_and_approval: >
  All actions are read/write inside the task working directory and the
  `/root/results/` output tree. No network or destructive ops. Tuning
  is fully autonomous — write the full output bundle for every command
  even when it fails success criteria, so the evaluator sees the
  metrics. Re-tune failing commands rather than aborting the batch.

steps:
  - name: ingest-environment
    description: >
      Load `system_params.yaml` via `scripts/run_one.py::load_system_params`.
      Extract mass, inertia (Ixx, Iyy, Izz), arm_length, kappa
      (drag-to-thrust), max_thrust_per_motor, tau_motor, g, motor_dirs,
      and the three acceleration limits (accel_limit_up,
      accel_limit_down, accel_limit_horiz). Resolve simulator dt
      (default 0.005 s = 200 Hz). List every file in `commands/` and
      parse each with `scripts/parse_command.py::parse_command`.
  - name: plan-trajectory
    description: >
      For each command, call `scripts/trajectory_planner.py::plan_trajectory`
      with the command's mode, start, end, T, dt, and the three accel
      limits. The planner returns a `(15, N)` desired-state matrix from
      a C² quintic profile (peak |s''| = 10/sqrt(3) ≈ 5.7735). If the
      requested T would exceed any axis's accel limit, the planner
      auto-extends T to the minimum feasible value and sets
      `extended=True`. Hover holds the endpoint with zero
      velocity/acceleration for the full duration.
  - name: build-cascade-pid
    description: >
      Construct `cascade_pid.CascadePID` with mass, g, arm_length,
      kappa, and max_thrust_per_motor from system_params. The outer
      loop converts (pos_err, vel_err, a_des) into a world-frame
      acceleration demand, adds gravity feed-forward, and derives
      `(phi_des, theta_des)` from the demand's direction. The inner
      loop converts attitude/rate error to body torques. Mixer
      (X-config) splits thrust+torques into per-motor thrusts. Mixer
      and dynamics must agree on motor numbering and CCW/CW signs —
      see references/dynamics_reference.md.
  - name: simulate
    description: >
      Run `quadrotor_dynamics.Quadrotor` (RK4 rigid-body integrator,
      Euler-step motor lag) for `N = planned.shape[1]` ticks. Init
      state at `planned[0:3, 0]` with zero velocity/attitude/rate.
      Record actual `(15, N)` matrix with `world_accel()` in rows
      12:15.
  - name: tune-gains
    description: >
      Call `scripts/tune_gains.py::tune(simulate_fn, baseline, mode)`
      with mode-specific baselines from
      `references/baseline_gains.md`. The search runs three rounds —
      coarse vertical, fine vertical, then horizontal — and stops
      early when `sse<0.05`, `overshoot_pct<5`, and `max_pos_err<0.05`
      all hold. Cost function in `references/tuning.md`. Reuse the
      previous command's tuned gains as starting point when consecutive
      commands share a mode.
  - name: compute-metrics
    description: >
      Call `scripts/metrics.py::compute_metrics(planned, actual, dt,
      mode, settling_threshold=0.02)`. Returns
      `{mode, RiseTime, SettlingTime, Overshoot_pct,
      SteadyStateError}` — matches the required `metrics_3d.json`
      schema exactly. Computes on the command's primary scalar
      response: z for takeoff/land, projection onto displacement
      vector for fly, mean tracking error for hover.
  - name: emit-outputs
    description: >
      Create `/root/results/<id>/`. Write `metrics_3d.json`,
      `tuning_results.json` (use `tune_gains.gains_to_dict`),
      `planned_trajectory.npy`, `actual_trajectory.npy`, and
      `plots/{desired_vs_actual.png, errors.png,
      cumulative_errors.png}` via `plot_results.write_plots`. Schemas
      and row layouts in `references/output_contract.md`.
  - name: verify-success
    description: >
      Check all four conditions for each command: SteadyStateError<0.05,
      Overshoot_pct<5, per-axis max planned accel ≤ its limit,
      max_k‖actual[0:3,k]-planned[0:3,k]‖<0.05. If any fail, return to
      tune-gains for that command with the previous best as seed. Emit
      the bundle either way — never abort partial results.
    depends_on: [compute-metrics, emit-outputs]

decisions:
  - signal: Planner reports `extended=True` (requested T was too short
      for the per-axis accel limits).
    action: Use the extended T — the planner already adjusted. Do not
      override; violating accel limits is a hard fail criterion.
  - signal: Per-timestep position error spikes during the maneuver but
      steady-state error is fine.
    action: Increase the inner attitude loop's `kp_att` by 1.5x and
      `kd_att` by 1.2x; if still spiking, shorten dt to 0.002 s.
  - signal: SteadyStateError stuck > 0.05 m on z.
    action: Verify gravity feed-forward is applied (`a_cmd[2] += g`,
      `T = m·|a_cmd|`); only then add `ki_pos[2]` in 0.1 increments.
  - signal: Overshoot_pct > 5 in z on takeoff.
    action: Reduce `kp_pos[2]` by 20%, increase `kd_pos[2]` by 20%;
      confirm the planner is providing the quintic profile (not a
      step) to the position loop.
  - signal: Horizontal drift in hover or yaw spinning.
    action: Check mixer signs against motor_dirs in system_params.yaml
      — yaw torque sign mismatch between dynamics and mixer is the
      most common cause. See references/dynamics_reference.md.
  - signal: After Round 2 of tuning, cost still > 50.
    action: Stop tuning. Issue is structural — check accel-limit
      violation, mixer/dynamics motor-direction agreement, and that
      `init_state[0:3] == planned[0:3, 0]`.

modes:
  - name: per-command
    body: >
      Default. Loop over `commands/*.txt`, run the full pipeline per
      file, write its bundle, then move on. Use this for graded runs
      so a single command failure doesn't block the rest.
  - name: warm-start
    body: >
      When consecutive commands share kinematic mode (e.g., several
      "fly" of similar length), reuse the previous command's tuned
      gains as the tuner's baseline. Substantially shortens overall
      wall-clock without lowering pass rate.

search_shortcuts:
  - category: Scripts (load and call directly)
    body: >
      `scripts/parse_command.py` — regex parser for the four commands.
      `scripts/trajectory_planner.py` — quintic + accel-limit feasibility.
      `scripts/quadrotor_dynamics.py` — 6-DoF RK4 + first-order motors.
      `scripts/cascade_pid.py` — outer pos / inner att PID + mixer.
      `scripts/metrics.py` — step-response metrics matching the JSON
      schema. `scripts/tune_gains.py` — coarse-fine local search.
      `scripts/plot_results.py` — the three required PNGs.
      `scripts/run_one.py` — end-to-end driver for a single command.
  - category: References (load on demand)
    body: >
      `references/output_contract.md` — exact JSON and `.npy` schemas
      and success criteria. `references/baseline_gains.md` — starting
      values per command mode. `references/tuning.md` — cost
      function, search recipe, and stall-recovery table.
      `references/dynamics_reference.md` — equations of motion,
      Euler conventions, X-config mixer, common pitfalls.

scenarios:
  - need: Command file says "Take off to 5 m height in 3 seconds" with
      accel_limit_up = 5 m/s².
    context: >
      Quintic over T = 3 s, Δz = 5 m: peak accel
      = 5.7735 * 5 / 3² ≈ 3.21 m/s² < 5 m/s². T_used = 3 s
      (no extension needed).
    action: >
      Plan, simulate with takeoff baseline gains, tune; expect
      Round 0 to converge in ~3-5 trials. Init state on the ground
      (z=0); planner moves drone to (0,0,5).
    outcome: >
      SteadyStateError ≈ 0.01-0.02 m, Overshoot ≈ 1-3 %,
      max_pos_err ≈ 0.02 m. All four criteria satisfied.
  - need: Command file says "Fly from (0,0,5) to (10,10,5) in 5 seconds"
      with accel_limit_horiz = 5 m/s².
    context: >
      Per-axis Δ = 10 m, T = 5 s. Peak per-axis accel
      = 5.7735 * 10 / 25 ≈ 2.31 m/s² < 5 m/s². T_used = 5 s.
    action: >
      Plan, init drone at (0,0,5), use the "fly" baseline (stronger
      horizontal and attitude gains). Tuner usually settles in
      Round 1 (vertical fine) since vertical is constant.
    outcome: >
      SteadyStateError ≈ 0.01 m, Overshoot near 0 %,
      max_pos_err ≈ 0.03 m. Pass.
  - need: Command file says "Hover at 5 m height for 10 seconds".
    context: >
      No transient — planner returns constant (0, 0, 5) for all N
      samples. Step-response metrics degenerate to a stability check.
    action: >
      Init drone at (0,0,5). Reuse takeoff baseline gains. Metrics:
      RiseTime = SettlingTime = Overshoot_pct = 0;
      SteadyStateError = mean Euclidean error over final 10 % of
      samples.
    outcome: >
      SteadyStateError < 0.01 m if gravity FF is correct. If drifts,
      check the `decisions` row on horizontal drift.
  - need: >
      Command file says "Take off to 10 m height in 2 seconds" with
      accel_limit_up = 4 m/s².
    context: >
      Quintic at T = 2 s, Δz = 10 m: peak accel
      = 5.7735 * 10 / 4 = 14.4 m/s², over the 4 m/s² limit.
      Planner reports `extended=True`,
      T_used = sqrt(5.7735 * 10 / 4) ≈ 3.80 s.
    action: >
      Accept the extended duration. Plan and tune against
      T_used = 3.80 s, not the original 2 s. Inform the evaluator via
      `plan_meta.extended = True` in your run log — the planned
      trajectory in the npy still reflects the extension.
    outcome: >
      Trajectory satisfies the accel-limit success criterion. The
      requested 2 s is unsatisfiable under the given limit; the
      next-best feasible solution is what the evaluator scores.

anti_patterns:
  - Feeding a step setpoint (constant `planned[0:3, k]` jumping
    instantaneously to the target) into the position loop instead of
    the quintic — guarantees accel-limit violation and overshoot fail.
  - Tuning the outer (position) loop before the inner (attitude) loop
    is closed and stable. Always seed `kp_att` / `kd_att` from
    baseline first; the outer loop's `(phi_des, theta_des)` only
    means something if attitude tracking works.
  - Setting `ki_pos` or `ki_att` to non-zero before `kp` / `kd` are
    settled — integrator windup will dominate short-maneuver behavior.
  - Skipping gravity feed-forward in the position-to-thrust mapping.
    The PID has to drive a non-zero steady-state thrust on its own —
    SteadyStateError will be biased.
  - Writing the `.npy` matrices with the wrong row layout. The exact
    order is pos / vel / orientation / angular velocity / acceleration,
    rows 0-2 / 3-5 / 6-8 / 9-11 / 12-14.
  - Computing `Overshoot_pct` on raw 3-D position. Use the command's
    primary scalar response — z for takeoff/land, projection onto
    displacement vector for fly. `metrics.compute_metrics` already
    does this; don't reimplement.
  - Mismatched motor-direction (CCW/CW) sign between
    `quadrotor_dynamics.py` and `cascade_pid.py` mixer — yaw torque
    inverts and the inner loop drives away from the setpoint.
  - Initial state not aligned with `planned[0:3, 0]`. First-tick
    Euclidean error already exceeds 0.05 m and the criterion fails
    regardless of how well tracking works afterward.
  - Aborting the batch when one command fails the criteria instead of
    writing its bundle and moving on. The evaluator inspects every
    command's outputs.
```
