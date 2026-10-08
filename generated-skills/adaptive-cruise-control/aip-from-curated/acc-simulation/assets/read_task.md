Read the task statement below and pin down everything the rest of the procedure needs.
Do not write any files yet.

Task statement:
{task_statement}

Environment directory (where the task's input files live): {environment_dir}

Produce ALL of these state keys now, even though the pause's `expects` lists only the first
two: later steps need every one of them (absolute paths everywhere; scripts run with cwd set to the pack's
scripts/ folder, so relative paths break):

- params_path: the vehicle parameters YAML (usually vehicle_params.yaml).
- sensor_path: the sensor CSV (usually sensor_data.csv; columns time, ego_speed, lead_speed,
  distance; empty lead_speed/distance = no lead vehicle detected).
- deliverable_dir: the directory the task wants outputs in (usually the environment
  directory, e.g. /root).
- deliverables: object with the exact file names the task asks for, keyed by role:
  pid_module (e.g. pid_controller.py), acc_module (e.g. acc_system.py), simulation_script
  (e.g. simulation.py), tuning_file (e.g. tuning_results.yaml), results_file (e.g.
  simulation_results.csv), report_file (e.g. acc_report.md). Use null for a role the task
  does not ask for; add extra keys for anything else it asks for.
- tuning_output_path: deliverable_dir joined with deliverables.tuning_file. If the task asks
  for no tuning file, use a path under deliverable_dir that it will not grade (e.g.
  .acc_tuning.yaml). Never point it at params_path: the original parameters file stays
  unmodified.
- results_path: deliverable_dir joined with deliverables.results_file.
- expected_columns: the exact output CSV column order the task states. If it states none,
  use ["time", "ego_speed", "acceleration_cmd", "mode", "distance_error", "distance", "ttc"].
- column_map: object mapping each task column name that stands for a reference column to that
  reference name (reference names: time, ego_speed, acceleration_cmd, mode, distance_error,
  distance, ttc), e.g. a task's speed/accel/gap -> ego_speed/acceleration_cmd/distance. Use
  an empty object when the task uses the reference names. If the task's CSV omits a column a
  target needs (distance_error for the distance target), still compute it internally but keep
  the CSV as the task specifies; the verify step will tell you if scoring is impossible.
- targets: object with the numeric acceptance targets the task states, under these keys
  (null when not stated): rise_time_max (s, speed 10%->90% of set speed), overshoot_pct_max
  (%), speed_ss_error_max (m/s), distance_ss_error_max (m), min_distance_min (m, safety gap
  that must never be violated). Common values: 10, 5, 0.5, 2, 5. A target the task implies in
  words ("must never get closer than 5 m") counts as stated.
- interface_requirements: verbatim class names, constructor and method signatures, return
  tuples, mode labels, CLI behavior, and any other code-level requirement the task states
  (empty string if none). Note anything the task says about how distance should be obtained
  (simulated from the ego's own motion vs. read straight from the sensor file).
