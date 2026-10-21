# Source and provenance: acc-pid-simulation

## Provenance

The five curated skills below are copied verbatim in this folder. They were compiled for the adaptive-cruise-control task: its statement (`instruction.md`) plus its real inputs, `vehicle_params.yaml` and `sensor_data.csv` (1501 rows, t = 0–150 s, lead present for t = 30–129.9 s), running in an Ubuntu 24.04 container with python3, numpy 1.26.4, pandas 2.2.2, pyyaml 6.0.1 and matplotlib 3.8.4.

| Source | Contributes |
|---|---|
| `csv-processing/SKILL.md` | Reading the sensor CSV with explicit NA handling, building result rows incrementally with `None` for missing values, `to_csv(index=False)` |
| `pid-controller/SKILL.md` | Control law, discrete `PIDController` (integral `+= e*dt`, derivative `(e - prev)/dt`, optional output clamp), anti-windup, manual tuning order, effect of each gain |
| `simulation-metrics/SKILL.md` | Rise time (10–90 %), overshoot %, steady-state error (final 10 %), settling time (2 %), copied verbatim into `scripts/evaluate.py` |
| `vehicle-dynamics/SKILL.md` | Kinematic speed update with `max(0, ·)`, gap update from relative speed, time-headway safe distance, TTC (None when not approaching), acceleration clamp, cruise/follow/emergency state machine |
| `yaml-config/SKILL.md` | `yaml.safe_load`, `yaml.dump(default_flow_style=False, sort_keys=False)`, FileNotFoundError and YAMLError handling, defaults for missing keys |

Facts found by functional testing against the real inputs, recorded as gotchas in SKILL.md:
- The recorded `distance` reaches 1.95 m at t = 121.6 s, when a cut-in forces hard braking. Replaying it fails the >5 m target, so the gap must be simulated.
- The recorded `ego_speed` ramps at 2 m/s², which gives a 12 s rise time. Copying it fails the <10 s target.
- The example output rows (`0.0,0.0,3.0` then `0.1,0.3`) fix the row semantics: state at t, then the command, then the update. They also imply a drag-free kinematic model.
- For t = 80–112 s the lead drives at up to about 35.8 m/s, above the 30 m/s set speed. With the set-speed cap the gap grows, and no gains can hold a 2 m distance error there. Likewise, during the post-emergency recovery (t ≈ 123–129 s) ego is already at +3 m/s² while the lead pulls away. The distance steady-state metric therefore excludes rows that are capped or saturated, and reports them separately.

## Component-kind choices

| Component | Kind | Why |
|---|---|---|
| `assets/pid_controller.py`, `assets/acc_system.py`, `assets/simulation.py` | execution (deliverable templates) | The control law, mode selection, TTC, clamping, anti-windup, gap integration and CSV format are deterministic rules. The task requires these exact files, so they ship as tested code rather than prose. |
| `scripts/tune_pid.py` | execution | Gain tuning is a numeric search against fixed thresholds. The manual tuning order from the source (Kp first, then Ki, then Kd) is encoded in the grids, and it reuses the deliverable's `run_simulation` so tuning and the final run cannot diverge. |
| `scripts/evaluate.py` | execution | Format validation, metrics, pass/fail thresholds and the report's fixed sections are all computable. A lookup table in the body maps each failing check to its remedy (deterministic branching on the script's output). |
| Decision `contract_check` (`contract_matches` choice, `targets_default` noul) | decision | Whether another task instance's interface or targets match the defaults needs a judgment of the statement against a fixed answer space. Later steps branch on the answer (edit the templates, pass `--target`). |
| Step 6, report review | client_task | Only an instance that asks for more than the template, or a logic change from step 1, needs new prose. That text has to be written by the agent. |
| Step 1 `differs` / `other` adaptation | client_task (conditional) | Changing code to a different interface means generating code. It is reached only through the decision. |

Alternatives considered and rejected:
- Replaying the sensor gap fails the safety target on the real data (above).
- Re-seeding the gap whenever the sensor distance jumps down (a cut-in) is physically closer. But the simulated ego is often faster than the recorded one at that moment, and re-seeding at t = 120 s gives a negative gap. The rule is to re-seed only when a lead reappears after a no-lead stretch.
- A single full joint grid (about 6500 simulations, over 2 minutes) was too slow. The staged search takes about 6 s.

## Deliberate-drop log

| Source item | Reason dropped |
|---|---|
| csv-processing: `df.head()`, `columns.tolist()`, `len(df)`, column/row filtering, `notna` filters, mean/max/min/std, adding computed columns, `iterrows` | Generic pandas the agent knows. The scripts use what they need directly. |
| csv-processing: `isnull().sum()` | Exploratory only. The scripts handle NaN per value (`_num`). |
| pid-controller: overview paragraph defining PID | Background. |
| pid-controller: anti-windup options "clamping" and "back-calculation" | One default is enough: conditional integration in `PIDController` (when limits are given) and in `AdaptiveCruiseControl`. The others are alternatives, not rules. |
| vehicle-dynamics: position update `x += v*dt` | Not needed. The gap is integrated directly from relative speed, which is equivalent and needs no absolute positions. |
| yaml-config: "return defaults when file missing" for the gains file | Deliberately reversed for `tuning_results.yaml`. The task requires gains read from it, so a missing file is a loud error rather than a silent default. Defaults are still used for missing keys in `vehicle_params.yaml`. |
| yaml-config: `allow_unicode=True` option | The output is ASCII numbers only. |
| simulation-metrics: "Usage" example | Superseded by `scripts/evaluate.py`'s CLI. |
| vehicle_params.yaml `mass`, `drag_coefficient` | Informational. The example output rows require the drag-free kinematic model (recorded as a gotcha, not silently ignored). |
