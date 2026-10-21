---
name: acc-pid-simulation
description: Build, tune, and evaluate an Adaptive Cruise Control (ACC) simulation in Python - PIDController class, AdaptiveCruiseControl with cruise/follow/emergency modes (time-headway gap, TTC emergency braking), a kinematic vehicle simulation driven by recorded lead-vehicle sensor CSV data, grid-search PID tuning to tuning_results.yaml, simulation_results.csv, rise time / overshoot / steady-state error / minimum-gap metrics, and an acc_report.md. Use for ACC, cruise-control or car-following PID tasks that read vehicle_params.yaml and sensor_data.csv.
compatibility: Python >= 3.8 with pandas and pyyaml (numpy comes with pandas). No other tools. Matches the task container (python3 + pandas 2.2.2 + pyyaml 6.0.1).
---

# ACC PID Simulation

## Trigger When

1. A task asks for `pid_controller.py`, `acc_system.py`, `simulation.py`, `tuning_results.yaml`, `simulation_results.csv`, or `acc_report.md` for adaptive cruise control.
2. A vehicle must hold a set speed with no lead vehicle and a time-headway gap behind a detected lead, with TTC-based emergency braking.
3. PID gains for speed and distance loops must be tuned against rise-time, overshoot, steady-state-error, or minimum-distance targets.
4. Any closed-loop vehicle-following simulation driven by recorded `time, ego_speed, lead_speed, distance` data with YAML vehicle parameters.

## Purpose

Ships the three deliverable modules as tested templates, a tuner that grid-searches both PID loops through the same simulation code, and an evaluator that validates the results CSV, computes the control metrics, and writes the report. It encodes the non-obvious choices: simulate the gap instead of replaying the recorded one, anti-windup plus PID reset on mode change, a set-speed cap in follow mode, and exactly how each metric is measured.

## Gotchas

- **Do not replay the sensor `distance` column as the simulated gap.** It was recorded behind the *recorded* ego, not yours. In the reference data it drops to 1.95 m, so replaying it fails the >5 m minimum-gap target. `simulation.py` takes the sensor gap when a lead first appears (or reappears after a no-lead stretch), then integrates `distance += (lead_speed - ego_speed)*dt`.
- **Do not copy the sensor `ego_speed`.** Ego speed is simulated from the first row's value (≈0). The recorded ego ramps at 2 m/s² and its rise time is 12 s, which fails the target.
- Row semantics follow the example output: each row holds the state at time t and the command computed from it, and the next row's speed is `max(0, v + a*dt)`, so `0.0,0.0,3.0,cruise,,,` is followed by `0.1,0.3,...`. Use a pure kinematic model. Mass and drag in the YAML are informational, and adding drag breaks the example rows.
- Cruise rows leave `distance_error, distance, ttc` empty. `ttc` is empty whenever ego is not closing on the lead. Emergency rows still carry `distance_error` and `distance`.
- Mode logic: `cruise` if `lead_speed` (or distance) is None/NaN. Otherwise `emergency` if TTC < threshold. Otherwise `follow`. Emergency commands `max_deceleration` (−8).
- Integral windup at the 3 m/s² limit during the 0→30 m/s ramp is what causes overshoot. The templates freeze integration while saturated and reset both PIDs on every mode change.
- Follow mode is capped by `kp_speed*(set_speed - ego)`, so a lead faster than the set speed never drags ego above it. In those rows the gap grows and `distance_error` is large by design.
- `tuning_results.yaml` holds exactly `pid_speed` and `pid_distance` with `kp` in (0,10), `ki` in [0,5), `kd` in [0,5). `simulation.py` must read it at runtime and contain no tuning code.
- `PIDController.compute` integrates `error*dt` and differentiates `(error - prev_error)/dt` from `prev_error = 0`, so the first call with kd > 0 gives a derivative kick. Kd also amplifies the noisy sensor `lead_speed`, so the tuner usually picks kd = 0.

## Workflow

Run every command from this skill's folder. The task files are inputs and outputs in `/root`. Before the first script, check that `python3 -c "import pandas, yaml"` works. If it fails, name every missing module and stop. Do not install anything.

- [ ] 1. Read the task statement and answer decision `contract_check`.
- [ ] 2. Deploy the modules (script).
- [ ] 3. Tune the gains (script).
- [ ] 4. Run the 150 s simulation (deliverable script).
- [ ] 5. Validate, compute metrics, write the report (script). Loop back on failure.
- [ ] 6. Review the report (client task).

### 1. Decision `contract_check` (input: the task statement)

```yaml
contract_matches:
  type: choice
  instructions: >
    Compare the task's required interface with the templates' contract:
    files pid_controller.py / acc_system.py / simulation.py in /root;
    PIDController(kp, ki, kd) with reset() and compute(error, dt);
    AdaptiveCruiseControl(config).compute(ego_speed, lead_speed, distance, dt)
    -> (acceleration_cmd, mode, distance_error) with modes cruise/follow/emergency;
    CSV columns time,ego_speed,acceleration_cmd,mode,distance_error,distance,ttc;
    tuning_results.yaml keys pid_speed/pid_distance with kp/ki/kd.
  criteria:
    matches: Every name, signature, column, key, and path above is what the task asks for.
    differs: The task renames or reorders something above, or uses other paths. The logic is the same.
    other: The task wants different control logic (other modes, another vehicle model, extra outputs).
targets_default:
  type: noul
  instructions: >
    Are the task's targets exactly rise time < 10 s, overshoot < 5 %, speed steady-state
    error < 0.5 m/s, distance steady-state error < 2 m, minimum distance > 5 m?
  criteria:
    true: All five appear with these values, or the task gives none.
    false: At least one value differs or one is missing.
```

A false `matches` is the costly mistake because it ships the wrong interface. If any name or column differs even slightly, answer `differs`.
- `matches`: go to step 2 unchanged.
- `differs`: after step 2, edit the copied files in `/root` to match the task, such as renamed columns in `COLUMNS` or other file paths. Keep the logic. The evaluator expects the default columns, so for renamed columns, check the renamed CSV by hand against the step 5 metric table.
- `other`: after step 2, extend the copied modules for the extra behaviour. Keep the gap-simulation and anti-windup rules from Gotchas.
- `targets_default` false: add `--target KEY=VALUE` for each differing target to both step 3 and step 5. The keys are `speed_rise_time`, `speed_overshoot`, `speed_ss_error`, `distance_ss_error`, and `min_distance`.

### 2. Deploy modules

```bash
cp assets/pid_controller.py assets/acc_system.py assets/simulation.py /root/
```

[assets/pid_controller.py](assets/pid_controller.py), [assets/acc_system.py](assets/acc_system.py), and [assets/simulation.py](assets/simulation.py) are the deliverables. Their docstrings carry the control law. Read `acc_system.py` before changing any control logic.

### 3. Tune gains

```bash
python3 scripts/tune_pid.py --workdir /root --log /tmp/tuning_log.json
```

[scripts/tune_pid.py](scripts/tune_pid.py) imports `run_simulation` from `/root/simulation.py` and runs about 850 closed-loop simulations in about 6 s:
- stage 1 grids the speed PID;
- stage 2 grids the distance PID for the 5 best speed sets;
- stage 3 refines the best set by ±25 % per gain.

Candidates that miss any target are rejected. The rest are ranked by the sum of metric/target ratios plus 0.05 per emergency event. It writes `/root/tuning_results.yaml` and exits 0 when a passing set exists. Exit 1 means only the best failing set was written. Use the failure table in step 5.

### 4. Simulate

```bash
python3 /root/simulation.py
```

This reads `vehicle_params.yaml`, `tuning_results.yaml`, and `sensor_data.csv` from the script's folder and writes `simulation_results.csv`, one row per sensor row (1501 for t = 0 to 150 s).

### 5. Evaluate and report

```bash
python3 scripts/evaluate.py --results /root/simulation_results.csv \
  --config /root/vehicle_params.yaml --sensor /root/sensor_data.csv \
  --gains /root/tuning_results.yaml --tuning-log /tmp/tuning_log.json \
  --report /root/acc_report.md
```

[scripts/evaluate.py](scripts/evaluate.py) exits 0 if the file is valid and all targets pass, 1 if a target fails, and 2 if the file is malformed (it lists the errors). It always prints the metrics JSON and, when given `--report`, writes the report with all three required sections.

Metric definitions:

| Metric | How it is measured |
|---|---|
| Rise time | 10 %→90 % of set speed in the first cruise segment |
| Overshoot | Maximum speed over all cruise rows |
| Speed steady-state error | Worst cruise segment of at least 5 s, measured as \|set − mean of its final 10 %\| |
| Distance steady-state error | Mean \|distance_error\| over steady follow rows: at least 5 s into follow, not capped at the set speed, command not saturated |
| Minimum distance | Minimum of the `distance` column |

Rows where the gap is not controllable are reported separately, not hidden.

On failure, change one thing, then rerun steps 3 to 5:

| Exit / failing check | Action |
|---|---|
| 2, column/row/time errors | Fix `simulation.py` output (columns, one row per sensor row, empty cruise fields) |
| `speed_rise_time` | Raise the lowest speed `kp` in `SPEED_GRID` |
| `speed_overshoot` | Check that anti-windup is intact and drop the high `ki` values from `SPEED_GRID` |
| `speed_ss_error` | Allow a small speed `ki` (0.01–0.05) |
| `distance_ss_error` | Widen `DIST_GRID` (`kp` up to 2, `ki` up to 0.2) |
| `min_distance` | Confirm the gap is simulated rather than replayed, then raise distance `kp` |

### 6. Client task: review the report

Read `/root/acc_report.md` against the task statement. It must cover system design (architecture, modes, safety features), the PID tuning method with final gains, and simulation results with metrics. Add any section or figure the task asks for that the template lacks, and describe any logic changed in step 1. Keep the numbers as the evaluator printed them.
