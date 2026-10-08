Write the report the task asks for ({deliverables}) in {deliverable_dir}. Skip this step
(output report_path = null) if the task asks for no report.

Facts to use (do not invent numbers; every figure comes from here):
- Configuration as loaded from the params file (its pid_speed/pid_distance are the INITIAL
  gains, before tuning): {config}
- Sensor data profile: {data_profile}
- Distance model: {distance_model}
- Tuned gains: {tuned_gains}
- Final verification and scorecard: {verification}
- Task statement (for any sections it requires): {task_statement}

Cover, in Markdown, at least the following plus any section the task names:
1. System design: speed PID (cruise), distance PID (follow, error = distance - (v *
   time_headway + min_distance), D term on the gap rate), follow command = min(speed,
   distance) so the car never exceeds set speed, emergency braking at max_deceleration when
   TTC < threshold, clamping to [max_deceleration, max_acceleration], kinematic vehicle
   model (v += a*dt, v >= 0; gap += (lead - ego)*dt), anti-windup and mode-switch resets.
2. PID tuning: method (grid search scored against the targets, speed loop first on the
   initial cruise segment, then the distance loop on the full run), initial vs. final gains,
   and what each gain does; if a tuned Ki or Kd is 0, say why the grid preferred it (e.g.
   a kinematic plant needs no integral action; the acceleration limit already bounds the rise) (Kp speed/overshoot, Ki steady-state error/oscillation, Kd
   damping/noise).
3. Results: a table of each metric with its target and pass/fail, mode counts, minimum gap,
   when emergency mode fired, and limitations (e.g. a lead faster than set speed cannot be
   followed, so the gap opens).
Output state key: report_path (absolute path of the report).
