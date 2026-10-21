# Adaptive Cruise Control (ACC) Simulation Report

## 1. System Design

### Architecture

The ACC is three Python modules:

- `pid_controller.py`: `PIDController(kp, ki, kd)` with `reset()` and `compute(error, dt)`. A discrete
  PID (`output = Kp*e + Ki*sum(e*dt) + Kd*(e - e_prev)/dt`). Output is clamped to the acceleration
  limits, and conditional integration provides anti-windup (the integral freezes while the output is
  saturated and the error would push it further).
- `acc_system.py`: `AdaptiveCruiseControl(config)` takes the nested `vehicle_params.yaml` dict and
  provides `compute(ego_speed, lead_speed, distance, dt) -> (acceleration_cmd, mode, distance_error)`.
  It runs two PID loops: speed (error = set speed - ego speed) and distance (error = gap - safe distance).
- `simulation.py`: reads the PID gains from `tuning_results.yaml` at runtime, takes lead-vehicle data
  (`lead_speed`, `distance`) from `sensor_data.csv`, and integrates a kinematic ego model
  (`v += a*dt`, `v >= 0`) for $rows steps of dt = $dt s. It writes `simulation_results.csv`.

The gap is propagated each step as `gap -= (ego_speed - lead_speed)*dt`. It is initialised from the
sensor `distance` when a lead vehicle is acquired. The recorded distance was measured from the human
driver's car, not from the simulated one, so it cannot be fed back directly once the simulated speed
diverges from the recorded speed.

### Operating modes

| Mode | Condition | Command |
|------|-----------|---------|
| cruise | no lead vehicle (`lead_speed` is None/NaN) | speed PID toward the set speed $set_speed m/s |
| follow | lead vehicle present and TTC >= $ttc s (or not closing) | `min(speed PID, distance PID)`, never above the set speed, never closing the gap |
| emergency | lead vehicle present and TTC < $ttc s | maximum braking $a_min m/s^2 |

Safe distance (time-headway policy): `d_safe = ego_speed * $time_headway + $min_distance` m.
`distance_error = distance - d_safe` (positive means the gap is larger than desired).
TTC: `distance / (ego_speed - lead_speed)` when closing, otherwise undefined (blank in the CSV).

### Safety features

- Acceleration command always clamped to [$a_min, $a_max] m/s^2.
- Emergency braking when TTC < $ttc s.
- Standstill gap of $min_distance m included in the spacing policy; speed cannot go negative.
- Both PIDs reset on every mode change, with the derivative memory primed to the current error so a
  mode switch causes no derivative kick. Anti-windup is applied on both loops.

## 2. PID Tuning Methodology

Tuning starts from the manual rules (set Ki = Kd = 0, raise Kp until the response is fast, add Ki for
steady-state error, add Kd for overshoot). These rules are automated as a two-stage
grid search. Every candidate gain set is scored by running the full $duration s simulation on the
recorded sensor data:

$tuning_log

1. **Speed loop first**, scored on rise time, overshoot, and cruise steady-state error.
2. **Distance loop next**, using the chosen speed gains, scored on steady-state gap error, minimum gap,
   overshoot, and the fraction of following time that settles.

A gain set that violates any target is penalised over every compliant one. Allowed ranges: $bounds
(kp exclusive at 0). $manual_note

### Final gains (`tuning_results.yaml`)

| Loop | Kp | Ki | Kd |
|------|----|----|----|
| Speed (`pid_speed`) | $ks_kp | $ks_ki | $ks_kd |
| Distance (`pid_distance`) | $kd_kp | $kd_ki | $kd_kd |

## 3. Simulation Results and Performance Metrics

Scenario profile (from `sensor_data.csv`):

| Interval | Lead |
|----------|------|
$segments

| Metric | Result | Target | Status |
|--------|--------|--------|--------|
| Speed rise time (10-90 % of set speed, initial cruise) | $rise | < $rise_t s | $rise_v |
| Speed overshoot (whole run) | $os | < $os_t % | $os_v |
| Speed steady-state error (final 10 % of each cruise segment, worst) | $sse | < $sse_t m/s | $sse_v |
| Distance steady-state error (mean abs, steady following) | $dse | < $dse_t m | $dse_v |
| Minimum distance | $mind | > $mind_t m | $mind_v |

$overall

Supporting figures:

- Settling time (2 % band, initial cruise): $settle; minimum TTC: $minttc.
- Steady following covers $dse_rows rows: follow mode, at least $settle_window s after the last mode
  change, set-speed cap, or actuator saturation. Worst steady error is $dse_max. The mean absolute
  error over all follow rows, transients included (lead pulling away beyond the set speed,
  recovery after emergency braking), is $dse_all.
- Time in mode: cruise $t_cruise s, follow $t_follow s, emergency $t_emerg s ($n_emerg emergency event(s)).
- Commanded acceleration range: $accel_lo to $accel_hi m/s^2.

### Input notes

$issues
