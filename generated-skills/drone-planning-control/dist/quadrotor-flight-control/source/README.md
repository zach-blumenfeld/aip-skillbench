# Source and provenance

`quadrotor-flight-control` was compiled from six curated Agent Skills that each covered one piece of a single workflow. The originals are copied verbatim in this folder:

| Source | Covers | Lands in |
|---|---|---|
| `flight-plan-parser/SKILL.md` | NL command → waypoints (4×n), times, modes | `scripts/flight_plan_parser.py`, SKILL step 3, Gotchas |
| `motor-model-dynamics/SKILL.md` | allocation matrix, RPM clip, motor lag, EoM, RK45, max thrust | `scripts/quad_model.py`, `references/model.md` |
| `position-controller-trajectory-planner/SKILL.md` | spline planner, position PID, output layout, accel limits, tuning table | `scripts/trajectory_planner.py`, `scripts/quad_model.py`, `scripts/run_commands.py`, SKILL steps 4 and 6, Gotchas |
| `attitude-controller-planner/SKILL.md` | attitude planner and PID, integral pattern, Ki cap, tuning table | `scripts/quad_model.py`, SKILL step 6 table, Gotchas |
| `stepinfo-3d/SKILL.md` | 3D rise/settling/overshoot/SSE | `scripts/stepinfo_3d.py`, `references/model.md`, Gotchas |
| `plot-quadrotor/SKILL.md` | three 5×3 figures | `scripts/plot_quadrotor.py`, `references/model.md` |

The task context came from `inputs/instruction.md` (output schema, success criteria, the four command forms), `system_params.yaml` and the Dockerfile (numpy 1.26.4, scipy 1.13, matplotlib 3.8.4, pyyaml 6.0.1; no other packages). None of the source skills shipped code, so every script was written for this skill. All scripts were functional-tested against the 30 real command files and 8 extra variants.

## Component-kind choices

| Component | Kind | Why |
|---|---|---|
| Preflight import check | execution | deterministic |
| Copy modules into /root | execution | deterministic; the task asks for simulator source in the container |
| Parse commands | execution (`flight_plan_parser.py`) | regex over a fixed grammar |
| `parse_matches_text` | decision (noul) | judging that the parse matches the sentence's intent needs reading the text; yes/no |
| Unrecognised wording → extend the regex | client task | needs new code for unforeseen phrasing |
| Plan + limits fallback, motor model, dynamics, PID, gain search, metrics, plots, saving | execution (`run_commands.py` + modules) | numeric calculations, thresholds, fixed rules |
| Success-criteria validation | execution (`check_results.py`) | fixed rules over the saved files |
| `failure_cause` | decision (choice) | classifying why a command failed means reading several signals; fixed label set mapped to actions |
| Symptom → gain-change table | reference table used after the decision | applied by the agent from the plots when the automated search is not enough |
| Final report | client task | synthesis text, given a template |

## Deliberate deviations from the sources (with rationale)

1. **Start waypoint.** The parser source says to auto-insert (0,0,0) at t=0. Here the start is the command's own start: ground for takeoff, (0,0,h) for hover/land, the from-point for fly. With (0,0,0) a hover becomes a climb and a land/fly starts with a jump. The stepinfo source itself assumes hover starts at the target.
2. **Spline boundary condition.** The sources say "cubic spline" without a bc. A 2-point default spline is linear, so `bc_type='clamped'` is used, one spline per segment, so each waypoint is a stop. This matches point-to-point modes.
3. **Accel-limit fallback (added).** The sources only state the limits. The planner switches a segment to an accelerate-coast-brake profile when the cubic's 6L/T² would break them, and reports infeasible commands.
4. **Tilt-compensated control (added, retry only).** The default is the source's small-angle law. The exact law is used only if the small-angle run misses a criterion, which helps aggressive horizontal moves.
5. **Gains.** The sources' "start small (kp_pos 0.1, kp_att [100, 100, 50]) and increase" gives errors far over 5 cm. Tested starting gains plus an automatic bounded search replace manual escalation. The tuning tables are kept for manual follow-up.
6. **tuning_results.json per command.** A source code comment says "same content for every command". The task says to tune per command, so each folder gets that command's best gains.
7. **stepinfo for hover.** The source returns all zeros when d0 ≈ 0. Here SteadyStateError is the true final distance, so drift is not hidden. It is ≈0 for a clean hover.
8. **Gain search integrator.** The search runs the same model with fixed-step RK4 (about 20× faster). The final saved run uses solve_ivp RK45 as the source specifies.
9. **plot_quadrotor** takes an optional `params_path` (default `/root/system_params.yaml`, as in the source), so it can be tested outside the container.
10. **Metrics `mode`** for a multi-line plan is the modes joined with `+`.

## Deliberate drops

- stepinfo usage snippet that prints each metric: trivial; the runner prints JSON summaries instead.
- "Circular / figure-eight → RMS error" guidance: kept in `references/model.md` as context only. The task's four command types are all point-to-point.
- Duplicate restatements across sources (output locations, saving the planned trajectory, dt rule, which appear 2–3 times): merged into one statement each.
- `motor_spread_angle`, `COM_vertical_offset` (yaml): the source model does not use them. Noted as unused in `references/model.md`.
- Repeated output-location code samples: replaced by the runner, which writes exactly that layout.
