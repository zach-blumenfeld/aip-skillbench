# Energy Market Pricing Report

Compile a complete market-pricing report from the results in state.

Required state keys:
- `base_results` — DC-OPF solve with dispatch, LMPs, binding lines, totals.
- `counterfactual_results` — present only if a counterfactual was run.
- `counterfactual_target` — the line that was relaxed.
- `counterfactual_scale` — multiplicative factor applied to the target line's rating.
- `impact` — base-vs-counterfactual deltas.

Produce one markdown document with these sections. Keep it tight and factual.
Dollar figures already round to 2 decimals; do not re-round or re-scale.

## System summary
A short paragraph with cost ($/hr), total load (MW), total generation (MW),
total reserves (MW), operating margin (MW), and reserve MCP ($/MWh).
Pull these from `base_results` (totals and `reserve_mcp_dollars_per_MWh`).

## Generator dispatch
A table with columns: id | bus | output_MW | reserve_MW | pmax_MW.
Source: `base_results.dispatch`. Preserve the given order.

## Locational marginal prices
A table of bus | LMP ($/MWh) sorted ascending by LMP so negative or depressed
prices read first; call out the lowest and highest in one sentence.
Source: `base_results.lmps`.

## Transmission congestion
List `base_results.binding_lines` (loading ≥ 99%). If empty, say "No binding
constraints — the system is uncongested in the base case." For each binding
line give from, to, flow_MW, limit_MW, loading_pct.

## Counterfactual analysis
If no counterfactual was run, say "Not requested — the system was uncongested
or the operator opted out." Otherwise include:
- The relaxed line (`counterfactual_target`) and the scale factor applied.
- Base cost, counterfactual cost, and cost reduction from `impact.cost_reduction_dollars_per_hour`.
- Whether `impact.congestion_relieved` is true and the before/after binding-line counts.
- A short table of the LMP changes with magnitude ≥ $1/MWh from `impact.lmp_deltas`,
  columns: bus | base_lmp | counterfactual_lmp | delta_dollars_per_MWh.
- One sentence of economic intuition: relaxing a binding constraint cannot
  increase cost (should be ≥ 0); a negative delta on bus LMPs means that
  bus got cheaper.

Return the rendered markdown as `report` (string).
