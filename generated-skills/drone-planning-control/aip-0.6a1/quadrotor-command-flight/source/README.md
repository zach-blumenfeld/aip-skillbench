# Source and provenance: quadrotor-command-flight

## Provenance

This skill compiles six curated Agent Skills into one procedure. The originals are copied
verbatim into this folder:

| Source | Covers |
|---|---|
| `flight-plan-parser/SKILL.md` | Natural-language command → waypoints (4×n), waypoint times, modes |
| `position-controller-trajectory-planner/SKILL.md` | Segment trajectory planner (15×max_iter), position PID, output layout, acceleration limits |
| `attitude-controller-planner/SKILL.md` | Acceleration → desired Euler angles, attitude PID, integral handling |
| `motor-model-dynamics/SKILL.md` | X-frame allocation, motor lag, 16-state nonlinear dynamics, RK45 stepping, thrust limits |
| `stepinfo-3d/SKILL.md` | 3D rise/settling/overshoot/steady-state metrics |
| `plot-quadrotor/SKILL.md` | The three 5×3 error-plot figures |

The task statement the skill targets: for each `commands/NNN.txt`, simulate the drone from
`system_params.yaml`, tune position and attitude PID gains per command, and write
`/root/results/NNN/{metrics_3d.json, tuning_results.json, planned_trajectory.npy,
actual_trajectory.npy, plots/}`. A command passes when steady-state error < 0.05 m,
overshoot < 5 %, the planned acceleration stays within `accel_limit_up/down/horiz` at
every timestep, and the position error is < 0.05 m at every timestep. Container: Ubuntu
24.04, python3 3.12, numpy 1.26.4, scipy 1.13.0, matplotlib 3.8.4, pyyaml 6.0.1.

## Intent and graph

1. `tune-and-simulate` (execution, `scripts/run_all.py`): the whole deterministic
   pipeline for every command file: parse, plan, check limits, simulate, grid-tune, score,
   write outputs. Every piece is code over structured inputs (regexes, splines, ODEs,
   PID laws, metric formulas, thresholds), so per the AIP kind order it is a script.
2. `by-run-status` (router on `run_status`): `all_pass` → end; `some_failed` → retry.
3. `plan-retry` (client_task, `assets/retry-task.md`): diagnosing a failure needs the
   agent: rewriting an unrecognised phrasing into a canonical command without changing
   its numbers, judging that a command is infeasible in the commanded time, or picking a
   new gain base from the symptoms. The output is free-form per label (rewritten text,
   gain vectors, reasons), so it is a client task rather than a decision.
   `references/quadrotor-reference.md` carries the domain detail on demand.
4. `rerun-failed` (execution, `scripts/rerun_failed.py`): applies the retry spec with a
   wide gain grid. It runs once; the procedure does not loop.
5. `end`: `results_dir` + `report`. Both keys exist on both paths. `retry_report` and
   `still_failed` exist only on the retry path, so they stay in the state but are not
   end inputs.

All physics and control code lives in one library, `scripts/drone_sim.py`, which the two
thin entry scripts import.

## Deliberate deviations from the sources (all verified by simulation)

| Source rule | Skill behaviour | Why |
|---|---|---|
| Cubic spline per segment (clamped cubic) | Minimum-jerk quintic; trapezoidal fallback when over the limit; infeasible flagged | The cubic's acceleration step at t=0 roughly doubled the tracking error (e.g. 0.052 → 0.023 m, 0.11 → 0.035 m on fast diagonals). The quintic's peak acceleration is also lower (5.77 vs 6 ·Δ/T²). |
| `F = m(g + acc_z)`; φ/θ "proportional to" `(…)/g` (small angle) | `F = m‖acc + g e3‖`; φ, θ by exact atan2 inversion of the ZYX thrust direction | The small-angle law lost altitude while tilted. A 4 m/s² diagonal failed at 0.35 m error and passed at 0.035 m with the exact law. It reduces to the source formulas for small tilts. |
| Parser auto-inserts the start at (0,0,0) | First command's start waypoint = where the command says the drone is: ground for takeoff, (0,0,h) for hover/land, the `from` point for fly | Starting a hover at 2 m from the origin would produce a 2 m error at t=0 and fail the per-timestep criterion. The instruction's hover and land commands imply the drone is already at h. |
| `parse_flight_plan` returns 3 values | Also returns unparsed lines | Feeds the router/retry path instead of silently dropping a command. |
| Trapezoid at the limit (not in source) | Trapezoid acceleration 30 % of the way from 4Δ/T² to 98 % of the limit | At the limit, motor saturation left no feedback authority (8.8 cm error). With headroom: 1.6–3.3 cm. |
| `tuning_results.json` "same content for every command" (code comment) | Best gains for that command | The task statement asks to tune per command. |
| plot reads `/root/system_params.yaml` itself | Gets `time_step` from the params file the caller passed | No hardcoded container path; another instance may put params elsewhere. |
| `trajectory_planner(waypoints, max_iter, waypoint_times, sample_rate, modes)` | Same plus `params`, returns `(traj, info)` | Needs the acceleration limits and reports per-segment profile/feasibility. Still no `question` argument. |
| 1D stepinfo for z-only maneuvers | `stepinfo_3d` for every mode | The output file is `metrics_3d.json` with one schema. For a z-only move the 3D distance equals the z error up to negligible x/y drift. |
| Suggested starting gains (`kp_pos 0.1`, `kp_att [100,100,50]`) | Base `kp_pos [12,12,16]`, `kd_pos [7,7,8]`, `kp_att [400,400,100]`, `kd_att [40,40,20]` and a 19-point grid | The source values were suggested as a starting point to increase from; they cannot hold 5 cm. The suggested values are kept in the reference and anti-patterns. |
| RK45 via `solve_ivp` | Kept for every simulation, including tuning | The 30 real commands × 19 gain sets, run in parallel across CPUs, take about 1.5 minutes even on a loaded machine. An earlier 37-point serial version took over 10 minutes under CPU contention and was cut back. |

## Component-kind choices

- The parser, planner, motor model, dynamics, controllers, metrics, plots, tuning, and
  criteria checks are all **scripts**. They are deterministic rules and numeric
  calculations.
- **Router** on the script's `run_status`. There is no LLM judgment in the branch.
- **Client task** only for failure diagnosis, which needs generated text and gain values.
- No decision step. Nothing before the retry needs a judgment over a fixed answer
  space, and the per-label retry answer is structured free-form output.

## Completeness check (source line → where it lives)

- flight-plan-parser: output format, the four patterns/modes, the stateful class
  (`FlightPlanParser`), the start auto-insert (changed, see above), per-type
  case-insensitive regex capturing only numbers, optional whitespace around commas, push
  the end waypoint + mode (N waypoints, N−1 modes), copy lists, top-level
  `parse_flight_plan`. These are in `drone_sim.py` and in the reference table; the usage
  example (shape (4,2), times [0,3]) was reproduced in testing.
- position-controller-trajectory-planner: segment-mode table (`trajectory_planner`,
  reference), separate yaw spline, signature, PID steps 1–5 (`position_controller`),
  `make_position_integral`, the output layout and file names (`run_command`, end step,
  reference), saving `planned_trajectory.npy` immediately after planning, the acceleration
  limit table read from params (`check_accel_limits`, purpose, reference), dt/time_final
  rules (anti-patterns, reference), no `question` arg, tuning table (reference).
- attitude-controller-planner: planner (changed, see above), returning rot/omega,
  controller steps 1–3 (`attitude_controller`), fresh integrals, ki_att ≤ 0.5
  (anti-pattern, reference), element-wise gains before `I @`, dt from params, tuning
  table (reference), main-loop order (`simulate`).
- motor-model-dynamics: allocation matrix, solve/clamp/sqrt/clip, lag, actual from the
  current rpm (`motor_model`), the 16-state layout and equations (`dynamics`), RK45
  stepping with held inputs (`simulate`), limits/T_max/T_min/twr formulas (`load_params`
  fallback, reference).
- plot-quadrotor: input layout, three files, save_dir argument, 5 groups × 3 axes, error
  and cumulative definitions, makedirs/savefig/close, figsize (16,20), LaTeX labels,
  blue/red (`plot_quadrotor`, reference).
- stepinfo-3d: metric definitions and steps 1–6 (`stepinfo_3d`, reference), target =
  last waypoint, default threshold 0.02 (task requires 0.02), limitations: hover → zeros,
  overshoot by distance, never-entered band → 0 (reference). Circular/figure-eight is a
  `do_not_use_when`.

## Deliberate drops

- `WaypointTrajectory` as a callable that advances `t_current` one sample per call and
  returns a quaternion. This is an implementation pattern. The skill evaluates the same
  per-sample position/velocity/acceleration directly into the 15-row matrix, which stores
  Euler angles, not quaternions, so the quaternion output has no consumer.
- The "1D metrics break for diagonal flight because axes are coupled" rationale.
  This is background for why the 3D metric exists. The skill uses the 3D metric
  everywhere.
- The motor-limits value table (3000 / 20000 / 36.5). These are example values
  identical to `system_params.yaml`, which the scripts read. Hardcoding them would break
  another instance.
- The usage code snippets (`from flight_plan_parser import …`, `from stepinfo_3d import
  …`, the per-command saving snippet). They are subsumed by `drone_sim.run_command`.
  The behaviours they show (paths, file names, `{'mode': mode, **metrics}`) are kept.

## Edge behaviour worth knowing

- When a hover-only command or a round-trip plan starts at its final target, every metric
  is 0 by the source definition. Tracking is still checked per timestep.
- A clean approach reports overshoot just under 2 %. The metric includes the
  band-entry sample (≤ 2 % of d0) by definition.
- Multi-line command files are supported. Segments chain in time; `mode` in
  `metrics_3d.json` is the last segment's mode.
- Paths in the start state must be absolute, because scripts run from `scripts/`.

## Functional test record (local `aip run`, packages from a scratch venv)

- The real 30 commands go through the `all_pass` branch to the end. All pass with max
  tracking error ≤ 0.011 m. Files were checked independently: shapes 15×(T·fs+1), JSON
  schemas, limits, errors.
- A crafted second instance (sample_rate 250, mass 0.85, recomputed limits) contained an
  unparsable phrasing, a 10 m / 2 s takeoff (infeasible), a trapezoid-only takeoff, an
  aggressive 3D fly, and a three-line plan. It went through `some_failed` → `plan-retry`
  (rewrite + skip) → `rerun-failed` → end. The rewritten command passed; the infeasible
  one was reported in `still_failed` with its reason. The gains-retry path was also
  exercised directly.
