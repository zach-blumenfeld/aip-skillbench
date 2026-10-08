The deliverables failed verification. Fix the cause, re-run the simulation script, then let
the procedure verify again.

Problems: {verification}
Deliverables: {deliverables} in {deliverable_dir}
Tuned gains: {tuned_gains} (file: {tuning_path})
Targets: {targets}

How to read the problems:
- columns / rows / time grid / mode labels / acceleration range / copied ego_speed: a
  porting or I/O bug in the deliverable code. Compare it against the pack's scripts/
  reference and fix it.
- "differs from the pack reference": the deliverable's control logic diverged; unless the task
  demanded that change, restore the reference logic.
- target missed on speed metrics: retune the speed loop: higher kp gives a faster rise; ki
  causes overshoot after saturation (keep anti-windup on); keep kd small.
- target missed on distance steady-state error: check that distance_error = distance -
  (ego_speed * time_headway + min_distance) and that the distance D term uses
  (lead_speed - ego_speed), not the derivative of distance_error (that one chatters). Then
  raise the distance kp/kd.
- min_distance missed: check the emergency trigger (TTC < emergency_ttc_threshold gives
  max_deceleration) and that the gap is propagated from the simulated ego speed.
If you change gains, write them to {tuning_path} in the same pid_speed / pid_distance shape and
update tuned_gains in the state. Load references/acc-design.md for the tuning guidelines.

Output state keys: deliverable_files (list of absolute paths you changed or wrote).
