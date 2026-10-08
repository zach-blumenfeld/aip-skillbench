# Write the final report

The DC-OPF market clearing solved. Compact summary:

{solve_summary}

- Full results (every LMP, flow, dispatch; base, counterfactual, impact): `{results_path}`
- Draft report in the canonical field names: `{report_draft_path}`
- Required output path: `{output_path}`
- Request's format requirements and questions: {report_requirements}

Canonical draft shape (what `{report_draft_path}` holds):

{assets[report_schema]}

Where other quantities live in the full results file (`base_case` / `counterfactual` blocks share keys):
`totals` (cost, load, generation, reserve), `operating_margin_MW`, `reserve_mcp_dollars_per_MWh`,
`reserve_requirement_MW`, `lmp_stats` (min, max, mean, `load_weighted_mean`, `n_negative`),
`binding_lines` (with `loading_pct`), `line_flows` (every branch: flow, limit, loading),
`generator_dispatch`, `checks`; `impact`: `cost_reduction_dollars_per_hour` (base - cf),
`cost_change_dollars_per_hour` (cf - base), `target_lines`, `congestion_relieved`,
`largest_lmp_drops` (most negative delta), `largest_lmp_rises`, `largest_lmp_changes` (largest
|delta|), `lmp_changes` (every bus), `binding_lines_added` / `binding_lines_removed`;
`self_check` / `self_check_cf`.

Do this:

1. If the requirements are "none specified" or exactly the canonical shape, copy the draft to
   `{output_path}` unchanged.
2. Otherwise build the required JSON from the draft and the full results with a short Python script
   (`json.load` both files; never hand-type numbers). Every quantity the request asks for must appear,
   even if the draft lacks it. Map names, not meaning: LMP list = `lmp_by_bus`; reserve price =
   `reserve_mcp_dollars_per_MWh`; binding lines = loading >= 99% of RATE_A; cost reduction =
   base - counterfactual; "largest LMP drop" = most negative `cf_lmp - base_lmp`; "largest change" =
   largest absolute delta. Top-N lists of any length come from `impact.lmp_changes` sorted accordingly.
   Keep every bus in `lmp_by_bus`; keep the solver's 2-decimal rounding unless the request asks otherwise.
3. Re-open `{output_path}` with `json.load` and confirm every required key is present with the right type.
4. Sanity-check before finishing (quote the numbers in your answer):
   - `checks.gen_minus_load_MW` ~ 0 and `checks.reserve_shortfall_MW` ~ 0 in each case.
   - `self_check` (and `self_check_cf`) `agrees` flags are true: dual prices match a +1 MW finite
     difference. If false, say so: duals can be non-unique in a degenerate LP.
   - Relaxing a constraint (higher line rating, lower reserve requirement) never raises cost; tightening
     one (higher load or reserve requirement) never lowers it.
   - Negative or very large LMPs at buses behind congested lines are valid, not errors.
   - If fewer buses changed price than a top-N list asks for (`n_buses_lmp_changed`), the remaining
     entries are zero-delta ties; keep the list length the request asks for and say so in your answer.
   - With a zero reserve price, total reserve procured may exceed the requirement slightly (a valid
     degenerate solution); report the solver's value.

Post `output_path` and `final_answer`: a short plain-text summary of the numbers the request asked
for (typically base and counterfactual cost, the cost change, reserve price, binding lines, whether
congestion on a target line was relieved, and the buses with the largest price moves).
