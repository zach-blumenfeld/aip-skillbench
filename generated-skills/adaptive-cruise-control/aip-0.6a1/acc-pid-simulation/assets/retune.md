The automated gain search for {meta.name} did not meet every ACC performance target. Before the
report is written, diagnose the failure and retune the gains by hand.

Targets: {targets}
Gains from the search (already written to tuning_results.yaml in {output_dir}): {tuned_gains}
Metrics of those gains, with per-target `checks`: {tuning_metrics}

Do this:
1. Read `references/acc-design.md` (failure diagnosis and tuning rules). Find which `checks` are
   false and why: an actuator limit, a target that cannot be met with these limits, a controller
   structure problem, or gains outside the grid.
2. Retune with the skill's `scripts/acc_common.py`. Run it from the skill's scripts folder with
   python3:
   - `python3 acc_common.py tune --output-dir {output_dir} --config {config_path} --sensor {sensor_path} --targets '<targets as JSON>' --speed-kp a,b,c --dist-kd x,y`
     reruns the two-stage search over grids you choose and rewrites tuning_results.yaml.
   - Or edit tuning_results.yaml by hand and run `python3 acc_common.py evaluate ...` with the same
     arguments to score it.
   Keep kp in (0,10), ki in [0,5), kd in [0,5).
3. Do not hardcode gains or tuning logic into simulation.py. It must read tuning_results.yaml. Do not
   relax a target, and do not edit the input files.
4. If a target is physically infeasible (for example, a rise time below 0.8 * set_speed / max_acceleration),
   leave the best compliant-elsewhere gains in tuning_results.yaml and say so.

Answer with `retune_notes`: which checks failed, what you changed, the final gains, and which checks
still fail (with the reason).
