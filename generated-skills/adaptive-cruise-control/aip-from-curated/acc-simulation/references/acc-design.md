# ACC design reference

Domain knowledge compiled from the five source skills (pid-controller, vehicle-dynamics,
simulation-metrics, csv-processing, yaml-config). Load it when you adapt or repair the
reference code, or write the report.

## PID control (pid-controller)

A PID (Proportional-Integral-Derivative) controller is a feedback mechanism. It continuously
computes an error and applies a correction from three terms:

    output = Kp * error + Ki * integral(error) + Kd * derivative(error)
    error  = setpoint - measured_value

- Kp, the proportional gain, reacts to the current error.
- Ki, the integral gain, reacts to the accumulated error.
- Kd, the derivative gain, reacts to the error's rate of change.

Discrete form, per step: `p = Kp*e`; `integral += e*dt`, `i = Ki*integral`;
`d = Kd*(e - prev_e)/dt` (0 if dt <= 0), then `prev_e = e`; output = p + i + d, optionally
clamped to [output_min, output_max]. `reset()` sets integral and prev_error to 0.

**Anti-windup.** Integral windup happens when the output saturates but the integral keeps
accumulating. There are three remedies:
1. Clamping: limit the integral term's magnitude (`integral_limit` in scripts/pid_controller.py).
2. Conditional integration: integrate only when not saturated (the reference default).
3. Back-calculation: reduce the integral while the output is clamped.

**Manual tuning.**
1. Set Ki = Kd = 0.
2. Increase Kp until the response is fast enough.
3. Add Ki to remove steady-state error.
4. Add Kd to reduce overshoot.

**Effect of each gain.**
- Higher Kp: faster response, more overshoot.
- Higher Ki: removes steady-state error but can cause oscillation.
- Higher Kd: less overshoot, but sensitive to noise.

ACC-specific findings from building this pack:
- The speed loop on a pure kinematic model needs no Ki. With kp ≈ 3 the command saturates at
  max_acceleration until the speed error is under 1 m/s, which gives the fastest possible rise
  with no overshoot. Large Ki with a slow Kp (the 0.1/0.01 defaults) overshoots by about 30%.
- The distance error contains -time_headway*ego_speed. Its numerical derivative therefore
  carries -time_headway*accel_prev, so with Kd*headway near 1 or above the command chatters
  between the limits. Feed the D term the gap rate (lead_speed - ego_speed) instead.
- Proportional-only distance control is undamped: the gap oscillates around the safe distance.
  The gap-rate D term supplies the damping.

## Vehicle dynamics (vehicle-dynamics)

- Speed update: `v_new = max(0, v + a*dt)`. Speed cannot be negative.
- Position update: `x_new = x + v*dt`.
- Gap to the lead: `relative = ego - lead`; `gap_new = gap - relative*dt`.
- Safe following distance (time-headway model): `speed*time_headway + min_distance`.
  time_headway is the time gap to keep in seconds; min_distance is the standstill gap in meters.
- Time to collision: `distance / (ego - lead)`. It is None when `ego - lead <= 0`
  (not approaching).
- Acceleration limits: `max(max_decel, min(a, max_accel))`. max_deceleration is negative
  (for example -8.0).
- State machine: no lead gives 'cruise'; a lead with TTC not None and TTC < threshold gives
  'emergency'; otherwise 'follow'. Use exactly these lowercase labels.

The YAML's mass and drag_coefficient are not used. The source model is kinematic, and the
drag coefficient alone, with no frontal area, cannot produce a force. Add drag only if the
task asks for it.

## Sensor data semantics

sensor_data.csv has the columns time, ego_speed, lead_speed and distance. Empty lead_speed and
distance mean no lead vehicle is detected. The recorded ego_speed and distance come from a
different drive. In a closed-loop simulation:
- Simulate ego_speed from your own commands. Start from the first recorded ego_speed.
- Take the lead's speed from the file.
- Seed the gap from the sensor distance when a lead is first detected, then propagate it with
  the simulated ego speed.

Copying the recorded distance can show gaps under 2 m that your controller never produced.
Write one output row per sensor row, on the same time grid. A lead faster than set_speed cannot
be followed (the ego is capped at set_speed), so the gap error grows in those stretches.

## Performance metrics (simulation-metrics)

- Rise time: the time from 10% to 90% of the target, scanning for the first sample at or above
  each level. None if the speed never reaches them.
- Overshoot %: `(max - target)/target*100`, or 0 if max <= target.
- Steady-state error: `|target - mean(last 10% of samples)|`.
- Settling time: the first time after which the signal stays within ±2% of the target (resets
  whenever it leaves the band).

Example usage:

```
times = [row['time'] for row in results]
values = [row['value'] for row in results]
target = 30.0
rise_time(times, values, target); overshoot_percent(values, target); steady_state_error(values, target)
```

For ACC, compute the speed metrics on the initial cruise run (start to first lead detection),
with target = set_speed. Compute the distance error on steady following stretches; the
scorecard in scripts/metrics.py documents its exact window.

## CSV handling (csv-processing, pandas)

- Read with `pd.read_csv(path, na_values=['', 'NA', 'null'])` and check `df.isnull().sum()`.
- Test single values with `pd.isna(x)`.
- Select columns with `df['col']` or `df[['a', 'b']]`; filter with
  `df[(df['time'] >= 30) & (df['time'] < 60)]`; keep non-null rows with `df[df['col'].notna()]`.
- Build results incrementally: append one dict per step to a list, then
  `pd.DataFrame(rows).to_csv(path, index=False)`. Use None for "not applicable" so the cell is
  written empty.
- Stats: `.mean() .max() .min() .std()`. Computed column: `df['diff'] = df['a'] - df['b']`.
  Iterate with `for i, row in df.iterrows()`.
- Inspect a file with `df.head()`, `df.columns.tolist()` and `len(df)`.

## YAML handling (yaml-config)

- Always use `yaml.safe_load`, which prevents code execution. Access nested values as
  `config['section']['key']`.
- Write with `yaml.dump(data, f, default_flow_style=False, sort_keys=False)`.
  default_flow_style=False gives block style, sort_keys=False keeps insertion order, and
  allow_unicode=True keeps unicode characters.
- Error handling: on FileNotFoundError fall back to defaults; on yaml.YAMLError report the
  error and fall back to defaults. An optional config is loaded as `safe_load(f) or {}` and
  merged over the defaults; the reference load_config merges nested keys.
