# Source and provenance: acc-pid-simulation

## Provenance

The five curated Agent Skills below are copied verbatim in this folder. They were compiled into one
AIP skill for the Adaptive Cruise Control simulation task: PID controller, ACC system, simulation,
gain tuning, results CSV, and report.

| Source | Content |
|---|---|
| `csv-processing/SKILL.md` | pandas CSV read/write, missing values, incremental rows, stats |
| `pid-controller/SKILL.md` | control law, discrete PID class, anti-windup options, tuning rules |
| `simulation-metrics/SKILL.md` | rise time, overshoot, steady-state error, settling time |
| `vehicle-dynamics/SKILL.md` | kinematic updates, time-headway safe distance, TTC, accel clamp, mode state machine |
| `yaml-config/SKILL.md` | `safe_load`, nested access, `dump` options, error handling, optional loading |

The design was also checked against the task statement (`instruction.md`: interfaces, CSV format,
gain ranges, targets) and against the real task inputs (`vehicle_params.yaml`, `sensor_data.csv`:
1501 rows, lead present 30.0–129.9 s, cut-in at 120.0 s where the recorded distance falls to 1.95 m).

## Intent

A downstream agent receives the task statement and runs this skill with the container paths. Scripts
do everything deterministic: they write the modules, search the gains against the recorded drive,
simulate, verify the deliverable contract, and write the report. The agent's own judgment is only
needed when the search cannot meet a target.

## Component-kind choices

| Step | Kind | Why |
|---|---|---|
| profile-inputs | execution | Config keys, CSV columns, dt, row count, lead segments, the rise-time feasibility bound, and constraint cross-checks are fixed rules over structured inputs. |
| build-and-tune | execution | Writing the modules is a file copy. Tuning is a numeric search with a computable objective (simulate, then score the metrics). |
| by-targets | router | Branches on the script's boolean `targets_met`; no judgment needed. |
| retune | client_task | Diagnosing why a target fails (actuator bound vs gains vs structure) and choosing new grids is open-ended. It needs agent reasoning plus the acc_common.py CLI. |
| simulate-and-report | execution | Running simulation.py, the CSV contract checks, the metrics, and filling the report template are deterministic. |

No `decision` step: every branch condition is a computed fact (targets met or not). An LLM judgment
would only add noise there.

Supporting files:

- `assets/pid_controller.py`, `assets/acc_system.py`, `assets/simulation.py`: the deliverable modules,
  written verbatim into output_dir.
- `assets/acc_report_template.md`: the report skeleton (string.Template).
- `assets/retune.md`: the client-task prompt.
- `scripts/acc_common.py`: metrics, grid search, and the evaluate/tune CLI.
- `references/acc-design.md`: deliverable contract, control and vehicle equations, metric
  definitions, tuning rules, the diagnosis table, and CSV/YAML handling.

## Design decisions not in the sources

- **Simulated gap, not the sensor distance.** The recorded distance belongs to the human driver's
  trajectory and reaches 1.95 m at the cut-in. The gap is initialised from the sensor when a lead is
  acquired and then propagated with `gap -= (v_ego - v_lead)*dt` (vehicle-dynamics). A cut-in while a
  lead is already present is applied through the lead_speed change, not by re-syncing the gap.
- **Row = state before the update**, which matches the task's example rows (0.0 then 0.3 at 3 m/s^2).
- **Follow = min(speed PID, distance PID)**; emergency = max deceleration. Both PIDs reset on a mode
  change, with prev_error primed, so a switch causes no derivative kick.
- **`PIDController.reset()` keeps the source's `prev_error = 0.0`.** Kick avoidance lives in the ACC,
  so the class behaves exactly as the source skill specifies.
- **Steady-state distance window.** Follow rows at least 5 s after a mode change, set-speed cap, or
  actuator saturation. A run with follow time and no steady rows fails. Without that rule the search
  found a high-Kd setting that chattered at the limits and "passed" on zero rows.

## Completeness check (line by line)

| Source item | Where it lives |
|---|---|
| csv: `read_csv`, inspect head/columns/len | profile_inputs.py (columns, rows, dt, segments) |
| csv: `na_values=['', 'NA', 'null']`, `isnull().sum()` | simulation.load_sensor_data, profile_inputs.py (half-missing rows counted); references §Data handling |
| csv: `pd.isna` per value | simulation._value, acc_system._missing |
| csv: column/subset/filter/notna access | profile_inputs.py, simulate_and_report.py checks |
| csv: `to_csv(index=False)`; build rows incrementally | simulation.main / run_simulation; anti_patterns |
| csv: mean/max/min stats | acc_common.compute_metrics |
| pid: control law, error = setpoint − measured | pid_controller.py, references §Control law, report |
| pid: discrete class (integral += e*dt, derivative, prev_error, output clamp) | assets/pid_controller.py |
| pid: anti-windup (clamping, conditional, back-calculation) | conditional integration + integral_limit in pid_controller.py; all three in references |
| pid: manual tuning steps | grid search stages (speed, then distance), report §2, references §Tuning rules |
| pid: effects of each gain | references §Tuning rules, diagnosis table |
| metrics: rise time 10–90 % | acc_common.rise_time (verbatim logic) |
| metrics: overshoot % | acc_common.overshoot_percent |
| metrics: steady-state error (final 10 %) | acc_common.steady_state_error, per cruise segment |
| metrics: settling time ±2 % | acc_common.settling_time, report |
| metrics: usage (target 30) | target = config set_speed |
| vehicle: speed update, max(0, ·) | simulation.run_simulation |
| vehicle: position update | references §Vehicle model (the gap update is used instead) |
| vehicle: distance update | simulation.run_simulation |
| vehicle: safe following distance | acc_system.safe_following_distance |
| vehicle: TTC, None when not approaching | acc_system.time_to_collision; blank ttc in the CSV |
| vehicle: acceleration clamp | acc_system.clamp, PID output limits, verification check |
| vehicle: mode state machine | acc_system.determine_mode |
| yaml: `safe_load`, nested access | simulation.load_yaml, acc_common.load_yaml, profile_inputs.py; anti_patterns |
| yaml: `dump(default_flow_style=False, sort_keys=False)` | acc_common.write_gains |
| yaml: YAMLError / FileNotFoundError handling | profile_inputs.py (fails with a clear message) |
| yaml: optional loading with defaults | ACC gain defaults when pid blocks are missing; `or {}` on empty files |

## Deliberate drops

| Item | Rationale |
|---|---|
| pid "Overview" paragraph (what a PID is) | Background the agent already knows. |
| csv `print(df.head())` exploration snippets | Replaced by the structured profile; printing to stdout would break the execution-step JSON contract. |
| csv `iterrows` and "add computed column" | Generic pandas. `to_dict('records')` is used instead because tuning runs hundreds of simulations and iterrows is slow. |
| yaml `allow_unicode=True` option | No unicode in the gains file. |
| yaml "return {} / defaults when the file is missing" fallback | Wrong for this task: a missing config or sensor file must stop the run, not silently simulate with defaults. Error handling is kept as fail-fast. |
| yaml generic `load_config(filepath, defaults)` merge helper | Only the gain blocks have sensible defaults; they are handled in AdaptiveCruiseControl. |
