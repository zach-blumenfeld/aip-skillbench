---
name: quadrotor-flight-control
description: Simulate a quadrotor drone (motor model, nonlinear dynamics with RK45), plan acceleration-limited trajectories from natural-language flight commands ("Take off to h m height in t seconds", "Hover at h m height for t seconds", "Land from h m height in t seconds", "Fly from (x,y,z) to (x',y',z') in t seconds"), tune cascaded position/attitude PID gains per command, and write per-command metrics_3d.json, tuning_results.json, planned/actual 15xN trajectory .npy files and error plots. Use for drone planning-and-control simulation tasks driven by system_params.yaml and a commands/ folder.
compatibility: Python >= 3.8 with numpy (1.26 OK), scipy (solve_ivp, CubicSpline), matplotlib, pyyaml. No other tools.
---

# Quadrotor Flight Control

## Trigger When

- A task gives drone `system_params.yaml` (mass, thrust_coefficient, rpm limits, inertia, accel limits) and natural-language flight commands, and asks for planned/actual trajectories, PID gains, step metrics, or plots.
- Asked to build a quadrotor simulator: motor RPM allocation + first-order lag, Euler-angle equations of motion, position and attitude PID loops.
- Asked to parse takeoff / hover / land / fly commands into waypoints, or to check a planned trajectory against `accel_limit_up/down/horiz`.
- Asked for 3D step-response metrics (rise, settling, overshoot, steady-state error on Euclidean distance) of a drone run.

## Purpose

Carries a complete, tested pipeline for "fly this command in simulation within 5 cm": a regex flight-plan parser, a piecewise clamped-cubic planner that falls back to a limit-respecting profile, an X-frame motor model with RPM clipping and 27 ms lag, nonlinear dynamics integrated with RK45, a cascaded PID (position → desired acceleration → roll/pitch → moments) with per-command gain search, `stepinfo_3d` metrics, three-figure plots, and an independent validator for the success criteria. It adds what an agent would get wrong unaided: where each command starts, why a default 2-point spline fails, which acceleration limit binds when braking, starting gains that work, and what the metrics mean.

## Inputs and outputs (task container)

- Commands: `/root/commands/*.txt`, one command per line (several lines = a multi-segment plan). Params: `/root/system_params.yaml`.
- Output per command file `NNN.txt` → `/root/results/NNN/`: `metrics_3d.json` (`mode`, `RiseTime`, `SettlingTime`, `Overshoot_pct`, `SteadyStateError`; settling_threshold 0.02), `tuning_results.json` (`kp_pos, ki_pos, kd_pos, kp_att, ki_att, kd_att`, 3 floats each), `planned_trajectory.npy` and `actual_trajectory.npy` (15 × max_iter: rows 0:3 pos, 3:6 vel, 6:9 φθψ, 9:12 pqr, 12:15 acc), and a `plots` folder holding `desired_vs_actual.png`, `errors.png`, `cumulative_errors.png`.
- Success per command: SteadyStateError < 0.05 m, Overshoot_pct < 5, planned acc within limits at every sample, ‖actual − planned position‖ < 0.05 m at every sample.

Re-read the task's instruction for its actual paths and use them in every command below if they differ.

## Procedure

Progress:
- [ ] 1 Preflight
- [ ] 2 Install the simulator source into the task
- [ ] 3 Parse check (decision `parse_matches_text`)
- [ ] 4 Plan, tune, simulate, save
- [ ] 5 Validate
- [ ] 6 Triage failures (decision `failure_cause`)
- [ ] 7 Report

### 1. Preflight (execution)

```bash
python3 -c "import numpy, scipy, matplotlib, yaml; print(numpy.__version__, scipy.__version__)"
```
If it fails, name every missing package (numpy, scipy, matplotlib, pyyaml) and install only those with `pip3 install --break-system-packages <names>`.

### 2. Install the simulator source (execution)

The task asks you to create the simulator, so put the modules into the container:
```bash
cp scripts/flight_plan_parser.py scripts/trajectory_planner.py scripts/quad_model.py \
   scripts/stepinfo_3d.py scripts/plot_quadrotor.py scripts/run_commands.py scripts/check_results.py /root/
```
Modules (each usable on its own): `flight_plan_parser.py` (`parse_flight_plan`), `trajectory_planner.py` (`trajectory_planner`, `WaypointTrajectory`, `check_accel_limits`), `quad_model.py` (`load_params`, `motor_model`, `dynamics`, `position_controller`, `attitude_planner`, `attitude_controller`, `make_position_integral`, `make_attitude_integral`, `simulate`), `stepinfo_3d.py` (`stepinfo_3d`), `plot_quadrotor.py` (`plot_quadrotor`), `run_commands.py` (driver), `check_results.py` (validator). Read `references/model.md` only if you need to change the physics, control law, planner, or metrics, or explain them.

### 3. Parse check (execution + decision)

```bash
python3 /root/flight_plan_parser.py /root/commands/*.txt
```
Prints modes, waypoint times, and the 4×n waypoint array (rows x, y, z, yaw) per file. An `Unrecognised flight command` error means the text uses wording the regexes do not cover. Extend the matching pattern in `PATTERNS` (client task) and rerun.

```yaml
parse_matches_text:
  type: noul
  instructions: For each command file, do the printed waypoints, times and modes match what the sentence says?
  criteria:
    true: Mode is right. Start is ground (takeoff), (0,0,h) (hover, land) or the from-point (fly). End is (0,0,h), (0,0,h), (0,0,0) or the to-point. Final time equals the stated seconds.
    false: Any number, start point, end point, mode or duration differs from the sentence.
```
A wrong plan corrupts every downstream file, so reconsider any close call that leans true. If false, fix the parser before step 4.

### 4. Plan, tune, simulate, save (execution)

```bash
python3 /root/run_commands.py --commands /root/commands --params /root/system_params.yaml --out /root/results
```
Per command: parse → plan (clamped cubic; trapezoid fallback if the cubic would break a limit) → save `planned_trajectory.npy` → gain search (≤ `--budget` RK4 runs, default 40, starting from the built-in gains) → final RK45 run → save actual, metrics, gains and plots. If the small-angle control law misses a criterion, the script retries with the exact tilt-compensated law and keeps the better result. Each command prints one JSON line: `pass`, `max_track_err`, the metrics, `accel` (peaks plus `up_ok/down_ok/horiz_ok`), `profiles`, `tilt_comp`. The last line is `k/N commands pass`. Exit 1 means at least one command failed. About 3 s per command.

Options: `--only 001 017` reruns selected labels. `--gains <gains.json>` sets the starting gains (tuning_results schema). `--no-tune` uses the starting gains as-is. `--budget 120` searches longer. `--tilt-comp` uses the exact law from the start.

### 5. Validate (execution)

```bash
python3 /root/check_results.py --commands /root/commands --params /root/system_params.yaml --out /root/results
```
It re-derives every criterion from the saved files: files present, exact JSON keys, (15, max_iter) shapes, finite values, accel limits, per-sample error, SSE, overshoot, and metrics that match a recomputation from `actual_trajectory.npy`. It prints `FAIL -> reasons` per bad folder. Exit 0 means all pass. Run it after every rerun.

### 6. Triage failures (decision), only for labels that fail step 5

Input: that label's JSON line from step 4 and its validator reasons.
```yaml
failure_cause:
  type: choice
  instructions: Why does this command fail?
  criteria:
    infeasible_accel: accel.ok is false. Even the minimum-peak profile breaks a limit, so the command cannot be flown in the stated time.
    saturated_plan: accel.ok is true but a planned peak is within ~5% of a limit (e.g. braking near accel_limit_up). Motors have no headroom left for feedback.
    aggressive_tracking: Limits hold with headroom, but max_track_err >= 0.05 and the planned horizontal accel exceeds ~5 m/s^2 (tilt > ~0.3 rad).
    gain_tracking: Moderate plan, but tracking error, SSE or overshoot misses its threshold.
    output_format: Validator reports missing files, wrong keys or shapes, or a metrics mismatch.
    other: None of the above.
```
Reconsider close calls between `gain_tracking` and `aggressive_tracking`. Picking gain_tracking for an aggressive plan wastes reruns.

Actions:
- `infeasible_accel` and `saturated_plan`: do not fake compliance by editing the plan or the files. Keep the outputs and report the command as physically infeasible or near-infeasible, giving the binding limit and the peak.
- `aggressive_tracking`: rerun `--only <label> --tilt-comp --budget 150`. If it still fails, report the label as beyond the cascaded controller's tracking ability. Include the peak horizontal accel and the error reached. Tested example: 6 m in 1.5 s, 10.9 m/s², still about 0.5 m of error.
- `gain_tracking`: rerun `--only <label> --budget 150`. If it still fails, write a gains JSON adjusted with the table below and rerun with `--gains`.
- `output_format`: fix the cause in `run_commands.py` (client task) and rerun that label.
- `other`: read `references/model.md`, diagnose, fix, and rerun.

| Symptom (from the plots / metrics) | Fix |
|---|---|
| Slow altitude response | Increase `kp_pos[2]` |
| Altitude overshoot | Increase `kd_pos[2]` |
| Persistent altitude offset | Increase `ki_pos[2]` |
| Slow roll/pitch correction | Increase `kp_att[0]`/`kp_att[1]` |
| Roll/pitch oscillates | Increase `kd_att[0]`/`kd_att[1]` |
| Yaw drifts slowly | Increase `ki_att[2]` |
| x/y oscillation during hover or z-only moves | Decrease `ki_pos[0:2]` and `ki_att` |

### 7. Report (client task)

```markdown
## Drone command results (<k>/<N> pass)
| label | command | mode | max err [m] | SSE [m] | overshoot [%] | accel ok | notes |
|---|---|---|---|---|---|---|---|
Failures: <label> — <failure_cause> — <binding limit/peak or what was tried>
Outputs: /root/results/<label>/…  Source: /root/*.py
```

## Gotchas

- **Start points.** Only takeoff starts on the ground. Hover and land start at (0,0,h) and fly starts at its from-point. A parser that always inserts (0,0,0) turns a hover into a climb.
- **Splines.** A 2-point `CubicSpline` with default bc is a straight line: constant velocity and a velocity step at t0. Use `bc_type='clamped'`. The clamped cubic peaks at 6·L/T² at both segment ends.
- **Braking limits.** The binding limit is often the braking one. Climbs brake with downward accel (`accel_limit_down`). Descents brake with upward accel (`accel_limit_up`, the smaller one).
- **Time base.** `dt = 1/sample_rate` from the yaml, never 0.005. `max_iter = round(T·sample_rate) + 1`, so t runs from 0 to exactly T. `time_final` comes from the parsed plan.
- **Initial state.** The planned state at t0, with motors at hover RPM √(mg/4c_T). Starting at rpm 0 or rpm_min makes the drone drop.
- **Integrals.** Create them fresh per run with `make_position_integral()` / `make_attitude_integral()`. A mutable default winds up across runs.
- **Attitude Ki.** Keep it 0 or small (≤ 0.5). Attitude wind-up causes x/y oscillation in z-only maneuvers.
- **Overshoot floor.** `Overshoot_pct` is the max distance after first entering the 2% band, so a run that enters the band reports about 2%, not 0. A run that never enters it reports 0. Hover (start = target) reports 0 for rise, settling and overshoot. SteadyStateError is still the true final distance.
- **Gains are per command.** Write each command's own `tuning_results.json`. Gains in every file are lists of 3 floats.
- **Planner arguments.** The planner takes `modes` from the parser, never the raw command text. Save `planned_trajectory.npy` right after planning.
- **Infeasible commands.** Report them. Never edit trajectories or metrics to pass.
