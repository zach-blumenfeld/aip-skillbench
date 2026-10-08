# Provenance

Compiled into one AIP procedure from six curated Agent Skills that together describe one workflow — build a quadrotor simulator, run every natural-language flight command through it, and write per-command results. Originals are copied verbatim in this folder:

| Source | What it contributed |
|---|---|
| `flight-plan-parser/SKILL.md` | Command grammar, stateful parser, (4×n) waypoints / times / modes format |
| `position-controller-trajectory-planner/SKILL.md` | Segment modes, WaypointTrajectory, trajectory_planner signature, position PID, acceleration limits, output layout (`results/NNN/…`), tuning table |
| `attitude-controller-planner/SKILL.md` | Attitude planner inverse kinematics, attitude PID, integral pattern, gain rules, tuning table, main-loop order |
| `motor-model-dynamics/SKILL.md` | X-frame allocation matrix, RPM clipping and lag, 16-state equations of motion, RK45 per step, thrust limits |
| `stepinfo-3d/SKILL.md` | 3D rise/settling/overshoot/steady-state-error definitions and their limitations |
| `plot-quadrotor/SKILL.md` | The three 5×3 figures, file names, cumulative-error formula, sample_rate from system_params.yaml |

Environment facts used (from the task's environment folder): Ubuntu 24.04 container with python3, numpy 1.26.4, scipy 1.13.0, matplotlib 3.8.4, pyyaml 6.0.1; `/root/system_params.yaml` (sample_rate 200, m 0.770, cT 8.07e-9, cQ 1.3719e-10, rpm 3000–20000, km 36.5, accel limits 6.962 / 9.429 / 13.602); `/root/commands/001.txt…030.txt`, one command per file (8 takeoff, 8 hover, 8 fly, 6 land). The pack's scripts use only those packages (PyYAML optional: a flat-YAML fallback parser is built in).

# Design

The sources are implementation instructions for modules an agent would otherwise write by hand. Everything deterministic is shipped as tested code in `scripts/quadsim/` (one module per source concept, named as the sources import them: `flight_plan_parser`, `trajectory_planner`, `position_controller`, `attitude_planner`, `attitude_controller`, `motor_model`, `dynamics`, `stepinfo_3d`, `plot_quadrotor`, plus `quad_params` and `simulate`). The procedure installs those modules where the task wants its source files and runs them; the agent only judges what code cannot.

## Step-kind choices

| Step | Kind | Why |
|---|---|---|
| `read-task` | client_task | Paths, code folder and numeric pass limits must be read out of free-form task text (generation of structured values from prose). |
| `prepare` | execution | Installing files, parsing commands, planning and checking limits are deterministic. |
| `interface-check` | decision (noul) | "Does the task demand interfaces the pack lacks?" is a yes/no judgment over the task text vs. the contract; threshold 0.2 because a missed mismatch breaks the task's tests. |
| `by-interface` | router | Branch on the noul. |
| `adapt-interfaces` | client_task | Writing wrappers/edits for task-specific names is code generation. |
| `by-feasibility` | router | Branch on the script's `all_feasible`. |
| `handle-infeasible` | client_task | Stretch vs. keep timing depends on how strictly the task words its timing; the choice is a boolean the scripts consume. Kept as a client task (not a decision) because it also produces a written justification. |
| `tune-gains` | execution | The gain sweep is numeric search. |
| `run-simulations` | execution | Simulation, metrics, file writing and re-verification are deterministic. |
| `by-result` | router | Branch on `all_pass`. |
| `retune` | client_task | Diagnosing failures with the symptom→fix tables and choosing new gains is open-ended; loops back to `run-simulations`. `accept_failures` ends the loop when criteria are unreachable. |

## Interpretations and additions (not in the sources, or resolving conflicts)

- **Start waypoint.** The parser source says both "auto-insert a starting waypoint at the current position" and "at (0,0,0)". `(0,0,0)` contradicts "Land from 2 m" and "Fly from (0,0,1)", and the stepinfo source says a hover command starts at the target. The pack uses (0,0,0) for takeoff and the position the first command states for hover/land/fly. The source's takeoff example is reproduced exactly.
- **Spline boundary conditions.** A 2-point `CubicSpline` with scipy's default not-a-knot is a straight line with a velocity jump. The pack fits a clamped cubic per non-hover segment (zero end velocity, peak accel 6·Δ/T²), so multi-command plans stop at each waypoint and every planned trajectory in the provided command set stays within the limits (largest: 3.33 m/s² down for 030).
- **Infeasible commands.** The sources state the limits but not what to do when a command breaks them. The pack checks every plan and offers stretching to the minimum feasible duration (+5%), decided per task in `handle-infeasible`.
- **Initial condition.** The vehicle starts at rest on the first trajectory sample with motors at hover RPM; starting at 0 RPM (below rpm_min) makes it fall before the loop reacts.
- **max_iter** = round((t_final − t0)·sample_rate) + 1 so the time vector ends exactly at `waypoint_times[-1]`.
- **Gains.** Passed through `params['kp_pos']` etc. because the sources' controller signatures `(current_state, desired_state, params, integral)` have no gain argument. Defaults are the sources' starting values.
- **Gain sweep.** The sources say "tuning_results.json — best PID gains from sweep" and give starting values but no method. The pack sweeps second-order parameterisations (kp = ω², kd = 2ζω) on the shortest command per mode plus the most aggressive one, then picks the lowest position bandwidth within 10% of the best cost, because the raw optimum (ωn = 8) sits next to unstable gain sets. On the provided commands the selection (ωn = 6, ωa = 24, ζ = 1) tracks every command with steady-state error ≤ 8 mm.
- **Metrics for z-only moves.** stepinfo-3d says pure z steps conventionally use 1D stepinfo on z; the output file is `metrics_3d.json` and the 3D distance equals |z − z_target| when x/y hold, so stepinfo_3d is used for every command. Rise time when the 10% band is never reached is reported as t[-1] (undefined in the source).
- **metrics_3d.json `mode`** for a multi-command file is the modes joined with `+`.
- **Plot params path** defaults to `/root/system_params.yaml` per the source, overridable with `params_path` or `$QUAD_PARAMS` so the pack can be tested outside the container.

# Deliberate-drop log

| Source content | Why dropped |
|---|---|
| Overview paragraphs in each source ("Two modules form…") | Restated by the module split and the step descriptions. |
| Python usage snippets (`from flight_plan_parser import …`, the `out_dir` saving block, the main-loop sketch) | Replaced by working code in `scripts/quadsim/` that does exactly this; the import names are preserved. |
| "Saving the Planned Trajectory" section | Duplicate of the output-layout block in the same source; carried by `run_all` (saves right after planning) and pack_contract. |
| "This file is used by the test suite to verify…" | Rationale; the limit check itself is carried by `check_accel_limits` in `prepare` and `run-simulations`. |
| `COM_vertical_offset`, `motor_spread_angle` params | No source uses them; the allocation matrix uses `arm_length` as written in the source. |

Everything else (formulas, tables, thresholds, rules, tuning tables) is carried in the scripts, `assets/pack_contract.md`, `references/model-reference.md`, `references/tuning-guide.md`, the templates, or the procedure's anti_patterns.
