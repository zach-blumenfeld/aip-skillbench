# acc-simulation: provenance and compilation notes

## Provenance

The pack was compiled from five curated Agent Skills that together describe one workflow:
build, tune and evaluate an Adaptive Cruise Control simulation. The originals are copied
verbatim:

| Source | Copied to | Contributes |
|---|---|---|
| csv-processing/SKILL.md | source/csv-processing/SKILL.md | pandas read with na_values, NaN checks, filtering, incremental results, to_csv(index=False), stats |
| pid-controller/SKILL.md | source/pid-controller/SKILL.md | control law, discrete PIDController, output clamping, anti-windup options, tuning guide, gain effects |
| simulation-metrics/SKILL.md | source/simulation-metrics/SKILL.md | rise time, overshoot, steady-state error, settling time |
| vehicle-dynamics/SKILL.md | source/vehicle-dynamics/SKILL.md | kinematic speed/position/gap updates, safe distance, TTC, acceleration clamp, cruise/follow/emergency state machine |
| yaml-config/SKILL.md | source/yaml-config/SKILL.md | safe_load, dump options, error handling, defaults merge |

source/environment-MANIFEST.md is the task environment's manifest. The pack was checked
against the real environment files: vehicle_params.yaml (vehicle, acc_settings, pid_speed,
pid_distance, simulation.dt) and sensor_data.csv (1501 rows at 0.1 s, columns
time, ego_speed, lead_speed, distance, with empty lead cells when no lead is detected). The
container provides numpy 1.26.4, pandas 2.2.2, pyyaml 6.0.1 and matplotlib 3.8.4; the
scripts use only pandas and pyyaml.

## What the sources did not say, found while building against the real data

- The recorded ego_speed and distance come from a different drive. The sensor distance
  falls to 1.95 m near t = 121 s, below any "minimum distance > 5 m" target. A closed-loop
  simulation must simulate ego speed and propagate the gap itself. The integrated model seeds
  the gap from the sensor on first detection, then applies `gap -= (ego - lead)*dt`, which is
  the vehicle-dynamics update. A third option was tried and dropped: reconstructing the lead
  position from the recorded ego plus the sensor distance gave negative gaps, because the
  recorded ego trace jumps (30 to 8.6 m/s at t = 130.4 s).
- With the default gains (0.1/0.01/0) the speed overshoots by about 30% and the gap
  oscillates, so tuning is mandatory.
- Differentiating the distance error (which contains -headway*ego_speed) feeds back
  -kd*headway*accel_prev. With kd*1.5 >= 1 the command chatters between +3 and -8. The distance
  loop's D term therefore uses the measured gap rate (lead - ego), passed through the new
  `derivative=` argument of PIDController.compute. Without that argument compute keeps the
  source behavior: a derivative from prev_error, which starts at 0.0.
- A lead faster than set_speed (about 261 rows in the real file) cannot be followed. The
  follow command is min(speed loop, distance loop), so the ego stays at or below set_speed.
- The best speed gains saturate at +3 m/s² until within 1 m/s, so the rise time is 8.0 s, the
  minimum the acceleration limit allows. Pure P (ki 0) is optimal on a kinematic plant. The
  tuner adds a small tie-break against Ki = 0 so the result stays a real PI(D) controller, and
  ki 0.01 costs 0.003% overshoot. On the real files it picks speed kp 3.0 / ki 0.01 / kd 0 and
  distance kp 0.8 / ki 0.01 / kd 0.8. Every target passes: rise 8.0 s, overshoot 0.003%, gap
  steady-state error 0.03 m, minimum gap 18.2 m, emergency braking at the t = 121 s hard stop.

## Functional test log

- Two runs of `aip run` / `aip resume` on synthetic full-length files in ./scratch (same
  format as the real ones) reached the end. One went through by-verification true; the other
  went through false, then repair, then true, after a deliberately wrong sensor-distance run
  (minimum gap 2.62 m).
- Two fresh agents ran the pack. One got the canonical task phrasing; the other a renamed
  single-file task (acc.py, columns time/speed/accel/mode/gap, no report). Both reached the end.
  They found:
  - verify passed vacuously on renamed columns. Fixed with the column_map key, and verify now
    fails when it cannot score.
  - the read-task pause's `expects` lists only two keys. The template now says to produce all
    keys.
  - a garbled distance-model sentence, an ambiguous python/default-path instruction, and the
    initial gains vs. tuned gains in the report. All rewritten.
  - a P-only speed loop. Fixed with the Ki tie-break.

## Step-kind choices

| Step | Kind | Why |
|---|---|---|
| read-task | client_task | Pulling file names, interfaces and numeric targets out of free-form task text is generation. The output is typed keys. |
| inspect-inputs | execution | Deterministic loading (yaml safe_load + defaults merge, pandas na_values) and profiling: time grid, lead segments, ranges, warnings. |
| choose-distance-model | decision (choice) | A judgment over the task text with a fixed answer space (integrated / sensor). Its threshold makes a borderline reading get reconsidered. |
| tune-gains | execution | Numeric grid search scored against thresholds. This is scriptable logic and must not be left to prose. |
| build-deliverables | client_task | The output is code in the task's requested names and signatures. The tested reference in scripts/ is ported, not rewritten. |
| verify | execution | Fixed rules: columns, row count/time grid, mode labels, acceleration limits, copied ego, reference reproduction, metric targets. |
| by-verification | router | Branches on the verify boolean. |
| repair | client_task | Fixing code or gains needs generation. It loops back to verify. |
| write-report | client_task | Prose synthesis, restricted to the numbers in the verification scorecard. |

Scripts: pid_controller.py, acc_system.py and simulation.py are both the reference deliverables
and the engine the step scripts import. metrics.py holds the simulation-metrics functions and
the scorecard. tune.py holds the grid search. inspect_inputs.py, tune_gains.py and
verify_outputs.py are the thin AIP step entry points (JSON on stdin, JSON on stdout).

## Source coverage (completeness check)

| Source item | Where it lives in the pack |
|---|---|
| csv: read_csv, head/columns/len | simulation.load_sensor; inspect_inputs profile (columns, rows); references/acc-design.md |
| csv: na_values, isnull().sum(), pd.isna | load_sensor na_values; inspect_inputs partial-row count; _num/_missing helpers; reference |
| csv: column access, filtering, notna | inspect_inputs and tune (lead_rows); reference |
| csv: writing from dict / incremental rows, index=False | simulation.simulate (row dicts) and main (to_csv index=False); reference |
| csv: mean/max/min/std, computed column, iterrows | metrics; reference "CSV handling" |
| pid: control law and term meanings | pid_controller.py docstring; reference |
| pid: discrete class, reset, compute, clamping | scripts/pid_controller.py (source semantics kept, prev_error starts at 0) |
| pid: anti-windup (clamping, conditional integration, back-calculation) | conditional integration in compute; integral_limit for clamping; all three in the reference; anti_patterns |
| pid: manual tuning steps and gain effects | reference; repair template; report template |
| metrics: rise_time, overshoot_percent, steady_state_error, settling_time, usage | scripts/metrics.py verbatim logic; scorecard; reference |
| vehicle: speed update with non-negative clamp, position, gap update | simulation.simulate; reference |
| vehicle: safe_following_distance | acc_system.py; distance_error definition |
| vehicle: time_to_collision (None if not approaching) | acc_system.py; ttc column empty when None |
| vehicle: clamp_acceleration | acc_system.py |
| vehicle: determine_mode state machine | acc_system.py; anti_patterns (labels) |
| yaml: safe_load, nested access | simulation.load_yaml / load_config |
| yaml: dump(default_flow_style=False, sort_keys=False), allow_unicode | tune_gains.py writes tuning YAML that way; reference lists the options |
| yaml: FileNotFoundError -> defaults; YAMLError -> message + defaults | load_yaml (missing -> {}, YAMLError -> stderr + {}) merged over DEFAULTS |
| yaml: load_config(filepath, defaults) merge | load_config (nested merge, tuning overlay) |

## Deliberate drops

- pid-controller "Overview" phrasing ("used in industrial control systems"): background only.
  The definition itself is kept in the reference.
- The csv-processing and yaml-config generic examples (`data.csv`, `config.yaml`, sample
  dicts like {'time': [0.0, 0.1, 0.2], ...}, `settings.param1`): illustrative placeholders.
  The patterns are kept and applied to the real files.
- The vehicle-dynamics position update `x += v*dt` is not tracked as an output column, because
  no ACC deliverable needs absolute position. Its effect is carried by the gap update, and the
  formula is in the reference.
- vehicle_params.yaml mass and drag_coefficient are loaded but unused. The source model is
  kinematic, and a drag coefficient without frontal area and air density cannot give a force.
  The reference says to add drag only if a task asks for it.
- The source PID returns raw output when output_min/max are None. That is kept. The ACC wires
  in the acceleration limits.
