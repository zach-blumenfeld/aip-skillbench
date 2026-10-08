# Adapt the model to a rule the solver script does not cover

`read-task` found a penalty or objective rule outside `absolute_deviation` / `shortfall_only`
(e.g. squared deviation, per-station weights, fixed vehicle cost, time windows, route-length caps).

1. Copy `scripts/solve_rebalancing.py` and `scripts/rebalance_common.py` from the skill folder
   (`{meta.name}`) to a working directory outside the skill folder; keep the copy's data loading,
   ID mapping, great-circle distance, arc-flow load, subtour elimination, extraction, and
   canonical-report writing intact.
2. Change only the part the task's rule touches, using the patterns in
   `references/rules-to-constraints.md` (linearise: never `abs()` or `max()` on solver expressions;
   squared terms → piecewise-linear or SCIP nonlinear objective via an auxiliary variable).
3. Run it with stdin `{{"currentState": <state>}}` and capture its stdout JSON.
4. Its stdout must contain `solution_path`, `objective`, `travel_distance`, `penalty_cost`,
   `total_deviation`, `solver_status`, `solver_gap`; `objective` must include the new terms.

Return JSON: the adapted script's stdout keys plus `"custom_objective": true` (the validator then
skips its standard penalty/objective recomputation, which no longer applies; verify those by hand).
