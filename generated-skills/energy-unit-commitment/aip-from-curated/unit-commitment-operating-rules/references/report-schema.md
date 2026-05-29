# Report JSON Schema — Reference

Load this when implementing `extract-report-arrays` and `finalize-report`.
The grader checks the exact field names and shapes below. Hour labels are
1-indexed. Thermal `production_MW` carries ACTUAL MW (including the pmin
contribution when committed), not above-minimum.

## Top-level structure

```json
{
  "case_name": "unit_commitment_schedule",
  "summary": {
    "solver_status": "optimal",
    "objective_cost": 123.45,
    "reported_mip_gap": 0.01,
    "time_periods": 48,
    "num_thermal_generators": 73,
    "num_renewable_generators": 81,
    "total_startups": 0,
    "total_shutdowns": 0,
    "max_demand_balance_violation_MW": 0.0,
    "max_reserve_shortfall_MW": 0.0
  },
  "thermal_generators": [
    {
      "name": "generator_id_from_input",
      "commitment":   [0, 1, 1],
      "production_MW":[0.0, 50.0, 55.0],
      "reserve_MW":   [0.0,  5.0,  6.0],
      "startup":      [0, 1, 0],
      "shutdown":     [0, 0, 0]
    }
  ],
  "renewable_generators": [
    {
      "name": "renewable_id_from_input",
      "production_MW": [0.0, 10.0, 12.0]
    }
  ],
  "hourly_summary": [
    {
      "hour": 1,
      "demand_MW": 0.0,
      "thermal_generation_MW": 0.0,
      "renewable_generation_MW": 0.0,
      "reserve_requirement_MW": 0.0,
      "scheduled_spinning_reserve_MW": 0.0
    }
  ],
  "constraint_check": {
    "demand_balance": "pass",
    "spinning_reserve": "pass",
    "reserve_deliverability": "pass",
    "generator_limits": "pass",
    "must_run": "pass",
    "ramping": "pass",
    "minimum_up_down": "pass",
    "startup_shutdown_logic": "pass",
    "initial_conditions": "pass",
    "renewable_limits": "pass",
    "cost_consistency": "pass"
  }
}
```

## Field rules

- **Generator names** match input names verbatim. Do NOT rename, prefix,
  or reorder.
- **Array lengths** equal `time_periods`. Every thermal and renewable
  generator from the input appears exactly once.
- **`commitment`, `startup`, `shutdown`** are integer 0/1 arrays. Solver
  floats must be rounded; tolerance is `1e-5` before rounding.
- **`production_MW`** is **actual** MW. When `commitment[t] = 0`,
  `production_MW[t] = 0`. When `commitment[t] = 1`,
  `pmin <= production_MW[t] <= pmax`.
- **`reserve_MW`** is the scheduled spinning reserve. Always
  nonnegative. Zero when offline.
- **`hourly_summary`** has exactly `time_periods` entries with `hour`
  starting at 1, incrementing by 1. `thermal_generation_MW` equals the
  column sum of `production_MW`; `renewable_generation_MW` equals the
  column sum of renewable `production_MW`;
  `scheduled_spinning_reserve_MW` equals the column sum of `reserve_MW`.
- **`summary.solver_status`** must be one of
  `{optimal, feasible, time_limit_feasible, suboptimal_feasible,
  heuristic_feasible}`.
- **`summary.reported_mip_gap`** is a nonnegative finite float, or `null`
  if you cannot determine it.
- **`summary.objective_cost`** must be the **recomputed** cost from the
  extracted arrays (piecewise interpolation + startup tier lookup), not
  the solver's reported objective. If you used `min(startup_tier_cost)`
  as the cost coefficient inside the solver, the solver's objective will
  understate startup cost; always recompute on extracted arrays.
- **`summary.max_demand_balance_violation_MW`** and
  **`summary.max_reserve_shortfall_MW`** are the per-period max of
  `|thermal+renewable - demand|` and `max(reserves - sum(r), 0)`
  respectively. Computed from extracted arrays.
- **`summary.total_startups`** = `sum(startup)`. Same for shutdowns.
- **`constraint_check.*`** must all be `"pass"` in the final report. The
  grader recomputes every check; setting `"pass"` here is a self-report,
  not a stand-in for the actual check.

## Recomputed-summary contract

The verdict returned by `scripts/validate_schedule.py` includes
`recomputed.summary` and `recomputed.hourly_summary` shaped exactly like
the corresponding fields above. Copy them verbatim into the report
before re-running the validator and marking `constraint_check.*` as
`"pass"`. This eliminates `cost_consistency` and `*_violation_MW`
drift between solver bookkeeping and the actual extracted schedule.
