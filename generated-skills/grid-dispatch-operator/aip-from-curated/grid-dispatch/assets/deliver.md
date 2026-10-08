Finish the dispatch task for {meta.name}.

Task request:
{task_request}

The solver wrote the report (default format) to: {report_written_to}
Solver status: {solver_status}
Summary: {report_summary}
Feasibility checks: {checks}
Notes: {notes}

Do this:
1. Read the task request for the exact output file path and JSON schema. If the requested
   keys, nesting, units, rounding, or line count differ from the default report
   (generator_dispatch: list of id, bus, output_MW, reserve_MW, pmax_MW; totals: cost_dollars_per_hour,
   load_MW, generation_MW, reserve_MW; most_loaded_lines: list of from, to, loading_pct;
   operating_margin_MW), load the written report with Python's json module and reshape it
   to the requested schema, then write it to the requested path. Never retype numbers by hand
   and never round more coarsely than asked.
2. If the task asks for a quantity the report lacks (e.g. a marginal cost, a specific
   line's flow, angles), compute it from the network file with the formulas in the reference,
   using the same dispatch, rather than estimating.
3. Sanity-check before finishing: power_balance_residual_MW ≈ 0, no limit or coupling
   violations, reserve_shortfall_MW ≈ 0 when reserves apply, n_overloaded_lines = 0 when
   network-constrained. A violation means the result is wrong; re-run instead of reporting it.
4. Values are rounded to 2 decimals (the source report format). If the task demands more
   precision, recompute that quantity from the network file rather than padding digits.
   Parallel circuits share from/to; tell them apart by branch_index (1-based branch row).
   If n_lines_tied_at_top_loading exceeds the number of lines requested, say in the answer that
   more lines are tied at that loading (the listed ones follow branch order).
   If the task demands MATPOWER's tap/phase-shift DC model, re-run the script with
   --matpower-taps (the default follows the sources' b = 1/X model).
5. Reply with `final_answer`: the output path(s) written plus headline numbers (cost,
   load, generation, reserves, operating margin, most loaded lines, and binding line limits when network-constrained; overloads when not).
