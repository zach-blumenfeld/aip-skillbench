These commands ask for more acceleration than the vehicle can produce with a clamped cubic profile (peak = 6·Δ/T² per axis; limits from system_params.yaml):

{infeasible}

Limits and vehicle data: {params_summary}

Task statement:
{task_statement}

Decide `stretch_infeasible`:
- `true` — lengthen each offending segment to the shortest feasible duration (+5% margin) so the planned trajectory respects the limits at every timestep. Choose this unless the task requires the commanded duration to be kept exactly: the planned trajectory is checked against the limits, and a trajectory over the limits saturates the motors and fails tracking anyway.
- `false` — keep the commanded timing; the results will report the violation.

Return JSON: `stretch_infeasible` (boolean) and `infeasible_note` (string: what was decided and why, naming the labels).
