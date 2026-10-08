Write the final output the task asks for.

Task instructions:
{task_instructions}

Validated solution: `{solution_path}` (JSON). Checks: {checks}
Recomputed cost: {recomputed_cost}   Solver: {solve_info}

The solution file holds, in source order: `thermal_names`, `renewable_names`, `commitment`, `startup`,
`shutdown` (0/1 per period), `thermal_dispatch_mw` (actual MW), `thermal_reserve_mw`,
`renewable_dispatch_mw`, optional `renewable_reserve_mw`, `system_totals` (generation, reserve, demand,
requirement per period), `recomputed_cost` (total, production, startup), `solver` (status, objective,
mip_gap, dual_bound, runtime_s), and `validation`. Per-resource fields are objects keyed by resource name
(in source order, matching `thermal_names` / `renewable_names`); each value is a list of length T indexed
by period, 0-based in source period order.

Rules:
- Use exactly the task's output path, file format, key names, nesting, resource IDs, period labels
  (1-based or timestamps if asked), and units. Do not add or rename fields the schema fixes.
- Build the file with a short script that reads the solution JSON; never retype numbers.
- Costs come from `recomputed_cost` (recomputed from arrays and input data), not from memory.
- Summary fields (totals, counts of starts, peak reserve, etc.) are recomputed from the arrays.
- If the schema has no status/gap field, still state in your final answer whether the schedule is
  optimal within the gap or a time-limited incumbent, with the gap.
- Self-check / "pass" fields may say pass only for families the validator passed; keep feasibility
  separate from proof quality: report the MIP gap from `solver.mip_gap`, and null/empty when no reliable
  bound exists (if the schema allows). Status: optimal-within-gap vs time-limited incumbent.
- Plain numeric values, deterministic ordering, no placeholders or NaN. Keep arrays at full precision
  unless the task asks for rounding; summary costs may be rounded to cents to strip float noise. If rounding is required,
  re-check that rounded generation still equals demand within the task's tolerance (adjust the last
  digit on a unit with headroom if needed).
- If the run relaxed an explicit task rule (debug step found it infeasible with the data), say so in the
  report if the schema has a place for it, and always in your final answer.
- After writing, reload the file and compare it against the required schema and the solution file.

Return a JSON object with `report_path` (the path written; comma-separated if several files) and `report_self_check` (one paragraph: schema
fields checked, shapes, cost and status values used).
