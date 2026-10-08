The UC run failed. Solve status: `{solve_status}`. Solver info: {solve_info}
Case: `{data_path}`. Solution file (may hold "validation" with failed checks): `{solution_path}`.
Validation violations, if any, are in the state as `violations`.

Diagnose before changing anything; first suspect the model encoding, not the data:

- `data_error`: read the listed errors; fix the mapping via a normalized file (new `data_path`).
- `no_incumbent` (time limit, no feasible point): raise `time_limit_s` (<= 1500) or loosen `mip_rel_gap`
  to 0.01-0.02; a time-limited incumbent is acceptable, no incumbent is not a solution.
- `non_integral`: binaries were not within 1e-4 of 0/1, so they were not rounded; tighten tolerances or
  re-solve (bad scaling or Big-M values are the usual cause), never round and report.
- `infeasible`: check, in order — initial min up/down obligations vs must-run; first-period ramp from
  power_output_t0 (shutdown at t=0 is blocked when power_output_t0 > ramp_shutdown_limit); post-horizon
  enforcement turned on without the prompt asking (`post_horizon_min_updown`); renewables forced to max
  (`renewables_must_use_max`) creating over-generation; demand + reserve above available capacity.
  Debug in stages: relax one family at a time or add diagnostic slack to balance/reserve in a scratch
  copy of solve_uc.py, print the largest violations, then remove the slack.
- If an explicit task rule makes the case infeasible (e.g. no curtailment while fixed renewables plus
  must-run/initially-forced minimum output exceed demand; see `data_warnings` from inspect-data), prove it
  with per-period arithmetic first, then relax only that rule minimally (e.g. allow curtailment) and carry
  the deviation forward so the report and your final answer disclose it. Never relax hard physical limits.
- Validation failed after an incumbent: a model row and its validation check disagree (see the
  row-to-check table in references/uc-model.md). Typical causes: total output mixed with output above
  minimum; startup/shutdown limits applied to the wrong quantity; `t` vs `t-1` index; startup tier
  convention; non-integral binaries rounded (max_binary_deviation large). Fix the model, never the
  validator, unless the validator contradicts the task's stated rule.

Common causes to rule out: bad Big-M values, segment/tier variables required when no start occurred,
cost curves treated as feasibility constraints, reserve on offline units.

Do not "repair" with a fixed-commitment LP unless it carries every family judged in the report (ramp,
reserve deliverability, startup/shutdown capability, min up/down); prefer re-solving the full model.
Edit the skill's scripts only for real formulation bugs; put experiments in a scratch directory.

Return a JSON object with the (possibly updated) keys the solve step needs: `data_path`, `time_limit_s`,
`mip_rel_gap`, and any convention booleans you changed.
