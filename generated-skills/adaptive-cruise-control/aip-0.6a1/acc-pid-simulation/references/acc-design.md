# ACC design, metrics, and tuning reference

Load this when a gain search misses a target (the retune step), or when you need to change a
delivered module.

## Deliverable contract (the task checks these exactly)

- `pid_controller.py`: `PIDController(kp, ki, kd)` with optional keyword args `output_min`,
  `output_max`, `integral_limit`. `reset()` sets `integral = 0.0` and `prev_error = 0.0`.
  `compute(error, dt) -> float`.
- `acc_system.py`: `AdaptiveCruiseControl(config)`, where config is the nested yaml dict
  (`config['acc_settings']['set_speed']`). `compute(ego_speed, lead_speed, distance, dt)` returns
  `(acceleration_cmd, mode, distance_error)`. Mode is `'cruise'` when lead_speed is None,
  `'emergency'` when TTC < threshold, and `'follow'` otherwise.
- `simulation.py`: reads gains from `tuning_results.yaml` at runtime, with no tuning inside. Uses
  `sensor_data.csv` for lead_speed and distance.
- `tuning_results.yaml`: `pid_speed` and `pid_distance`, each with `kp`, `ki`, `kd`. kp in (0,10),
  ki in [0,5), kd in [0,5).
- `simulation_results.csv`: one row per sensor row (1501 for 150 s at 0.1 s). Columns exactly
  `time,ego_speed,acceleration_cmd,mode,distance_error,distance,ttc`. Cruise rows leave the last three
  blank. Each row logs the state *before* the update, so the first rows read
  `0.0,0.0,3.0,cruise,,,` and then `0.1,0.3,3.0,cruise,,,`.
- `acc_report.md`: system design (architecture, modes, safety features), PID tuning methodology and
  final gains, and simulation results with performance metrics.

## Control law and structure

- PID: `output = Kp*e + Ki*integral(e) + Kd*de/dt`, discrete: `integral += e*dt`,
  `derivative = (e - prev_error)/dt` (0 if dt <= 0), then clamp the output.
- Error convention: speed `e = set_speed - ego_speed`, distance `e = distance - safe_distance`. With
  this convention a positive output means accelerate, for both loops.
- Follow mode: `a = min(speed_pid(e_v), distance_pid(e_d))`. Taking the minimum keeps the car below
  the set speed and stops it closing on the lead. Emergency: `a = max_deceleration`. Clamp to
  [max_deceleration, max_acceleration].
- Anti-windup options: (1) clamp the integral magnitude, (2) conditional integration (freeze the
  integral while saturated and the error pushes further; this is the default here), (3)
  back-calculation (bleed the integral when clamped). In follow mode the loop that loses the `min` is
  usually saturated, and conditional integration keeps it from winding up.
- Reset both loops on a mode change, and prime `prev_error` with the current error. Otherwise the
  first derivative term after a switch is `Kd*e/dt`, a kick of up to hundreds of m/s^2.

## Vehicle model

- `v_next = max(0, v + a*dt)`, `x_next = x + v*dt`, `gap_next = gap - (v_ego - v_lead)*dt`.
- Safe distance: `v_ego * time_headway + min_distance`.
- TTC: `distance / (v_ego - v_lead)` if `v_ego > v_lead`, otherwise None (not closing).
- Gap source: propagate the gap from the simulated ego speed and the recorded lead speed, and
  initialise it from the sensor distance when the lead is (re)acquired. The sensor distance belongs
  to the human driver's trajectory. In the reference data it drops to about 2 m during a cut-in at
  t≈120 s, so copying it into the simulation fails the minimum-distance target and ignores the
  controller entirely.

## Metrics (definitions used for tuning and the report)

- Rise time: 10% to 90% of the set speed, over the first cruise segment (the step from rest).
- Overshoot: `(max(v) - target)/target*100` when `max(v) > target`, else 0. Computed over the whole
  run.
- Speed steady-state error: `|target - mean(final 10% of values)|`, per cruise segment that lasts at
  least 10 s. The worst segment is reported.
- Settling time: start of the last entry into the ±2% band.
- Distance steady-state error: mean |distance_error| over steady follow rows. A row is steady when
  at least 5 s have passed since the last mode change, set-speed cap (gap > desired while
  ego ≥ set_speed - 0.5), or acceleration saturation. A run with follow time but no steady rows
  fails; that means the loop never settles.
- Minimum distance: the minimum of the simulated gap.

## Tuning rules

Manual tuning: set Ki = Kd = 0, raise Kp until the response is fast enough, add Ki to remove
steady-state error, then add Kd to reduce overshoot.
Gain effects: higher Kp is faster with more overshoot. Higher Ki removes steady-state error but can
oscillate. Higher Kd damps overshoot but is noise-sensitive (lead_speed in real data is noisy, about
±1 m/s).

Domain notes:

- The ego plant is a pure integrator (no drag in the kinematic model), so a P-only speed loop
  already has zero steady-state error. Ki mostly adds overshoot.
- Rise time is bounded below by `0.8*set_speed/max_acceleration` (8 s for 30 m/s at 3 m/s^2). To
  stay saturated until 90% of the set speed you need `Kp_speed >= max_accel/(0.1*set_speed)`.
- The time-headway term (`-time_headway*v_ego` inside the distance error) adds damping on its own,
  so a P or PD distance loop is usually enough. A large Kd makes the command chatter at the limits.

## Diagnosing a missed target

| Failed check | Likely cause | Try |
|---|---|---|
| rise_time | Kp_speed too low, or the target is below the physical bound | raise speed kp; if infeasible, report it |
| overshoot | integral windup or Ki too high | lower speed ki, add a little kd, check anti-windup |
| speed_ss_error | Kp too low or a cruise segment too short to settle | raise kp; inspect speed_ss_error_by_segment |
| distance_ss_error | distance loop too slow, or oscillating | raise dist kp; add kd if oscillating; check follow_steady_fraction |
| min_distance | late braking after a cut-in or hard lead braking | raise dist kp/kd; confirm emergency mode triggers (TTC threshold) |

## Data handling

- CSV: `pd.read_csv(path, na_values=['', 'NA', 'null'])`. Test for missing values with `pd.isna(x)`
  and treat a NaN lead_speed or distance as "no lead" (None). Write with `to_csv(path, index=False)`
  from a list of row dicts built incrementally. A None becomes an empty field.
- YAML: always `yaml.safe_load`. Write with
  `yaml.dump(data, f, default_flow_style=False, sort_keys=False)` to keep block style and key order.
  Catch `FileNotFoundError` and `yaml.YAMLError` with a clear message. `safe_load` of an empty file
  returns None, so use `or {}`.
