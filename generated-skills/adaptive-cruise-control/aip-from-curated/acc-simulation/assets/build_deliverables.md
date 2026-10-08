Write the task's code deliverables into {deliverable_dir} and produce the results CSV.

Deliverables requested: {deliverables}
Interface requirements from the task: {interface_requirements}
Distance model chosen: {distance_model}
Tuned gains (already written to {tuning_path}): {tuned_gains}
Results CSV to produce: {results_path} with columns {expected_columns}
Column renames (task column -> reference column): {column_map}
Sensor file: {sensor_path}   Params file: {params_path}

The pack's scripts/ folder holds a tested reference implementation; start from it instead of
writing new control code:
- scripts/pid_controller.py: PIDController(kp, ki, kd, output_min, output_max) with
  reset() and compute(error, dt, derivative=None); output clamping; conditional-integration
  anti-windup; rollback_integral().
- scripts/acc_system.py: AdaptiveCruiseControl(config) with compute(ego_speed, lead_speed,
  distance, dt) -> (acceleration_cmd, mode, distance_error) and last_ttc; helpers
  safe_following_distance, time_to_collision, clamp_acceleration, determine_mode.
- scripts/simulation.py: load_config (defaults <- params YAML <- tuning YAML), load_sensor,
  simulate(config, sensor, distance_model), CLI with --params --sensor --tuning --output
  --distance-model, defaults vehicle_params.yaml / sensor_data.csv / tuning_results.yaml /
  simulation_results.csv in the current directory.
- scripts/metrics.py: rise_time, overshoot_percent, steady_state_error, settling_time,
  scorecard (copy it only if the task asks for a metrics module or the report needs it).

Do this:
1. Copy pid_controller.py, acc_system.py and simulation.py into {deliverable_dir} under the
   requested file names. If a requested name differs from the reference name, rename the file
   and fix every import (acc_system imports `from pid_controller import PIDController`;
   simulation imports `from acc_system import AdaptiveCruiseControl`). If the task wants
   everything in fewer files, merge them.
2. Apply every interface requirement exactly (class/method names, argument order, return
   tuple, mode labels, column names). Keep the behavior: mode logic, clamping, the D term of
   the distance loop on (lead_speed - ego_speed), min(speed, distance) command in follow
   mode, mode-switch resets, empty cells (not 0, not "None") when no lead. If the task states
   a different rule than the reference (e.g. another emergency trigger), the task wins.
3. Chosen distance model: {distance_model}. Only when it is "sensor", run the simulation with
   --distance-model sensor (or make that the script default). "integrated" is the default.
4. Make the default paths match the task's file names (the reference defaults are
   vehicle_params.yaml, sensor_data.csv, tuning_results.yaml, simulation_results.csv,
   resolved against the current directory; change them if the task names differ, and
   resolve them against the script's own folder if the task may run it from elsewhere).
   Running `python <simulation_script>` from {deliverable_dir} with no arguments must read
   the task's params, sensor and tuning files and write {results_path}. Run it like that with
   the python that has pandas and pyyaml (the task container's python3).
5. When the task renames columns (column_map), rename them only at the CSV write and keep
   the internal names, so the logic stays identical to the reference.
6. Confirm {results_path} exists. Do not edit {params_path}.

Output state keys: deliverable_files (list of absolute paths you wrote).
Read references/acc-design.md if you need the control theory or a pitfall explained.
