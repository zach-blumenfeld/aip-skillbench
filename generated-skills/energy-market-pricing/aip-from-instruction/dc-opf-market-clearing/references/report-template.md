# Report template — required structure of `report.json`

The solver script writes this structure automatically when you pass `--report report.json` together with at least one `--override-line`. The fields below must appear exactly as named — downstream consumers parse by key.

```json
{
  "base_case": {
    "total_cost_dollars_per_hour": 12500.0,
    "lmp_by_bus": [
      {"bus": 1, "lmp_dollars_per_MWh": 35.2},
      {"bus": 2, "lmp_dollars_per_MWh": 38.7}
    ],
    "reserve_mcp_dollars_per_MWh": 5.0,
    "binding_lines": [
      {"from": 5, "to": 6, "flow_MW": 100.0, "limit_MW": 100.0}
    ]
  },
  "counterfactual": {
    "total_cost_dollars_per_hour": 12300.0,
    "lmp_by_bus": [
      {"bus": 1, "lmp_dollars_per_MWh": 34.0},
      {"bus": 2, "lmp_dollars_per_MWh": 35.5}
    ],
    "reserve_mcp_dollars_per_MWh": 5.0,
    "binding_lines": []
  },
  "impact_analysis": {
    "cost_reduction_dollars_per_hour": 200.0,
    "buses_with_largest_lmp_drop": [
      {"bus": 2, "base_lmp": 38.7, "cf_lmp": 35.5, "delta": -3.2},
      {"bus": 3, "base_lmp": 37.1, "cf_lmp": 34.8, "delta": -2.3},
      {"bus": 4, "base_lmp": 36.5, "cf_lmp": 34.9, "delta": -1.6}
    ],
    "congestion_relieved": true
  }
}
```

## Field semantics

- **`total_cost_dollars_per_hour`** — system-wide production cost at the LP optimum.
- **`lmp_by_bus`** — one entry per bus, indexed by the MATPOWER bus number (not array index). Order matches the bus list in the network file.
- **`reserve_mcp_dollars_per_MWh`** — single scalar (single-zone reserve market). Equals 0 when the reserve requirement is non-binding.
- **`binding_lines`** — every branch with `|flow| / rateA ≥ 0.99`. Empty list when nothing binds. `from`/`to` use bus numbers.
- **`cost_reduction_dollars_per_hour`** = `base.total_cost − counterfactual.total_cost`. Positive when the counterfactual reduces cost.
- **`buses_with_largest_lmp_drop`** — the **three** buses with the most negative `delta = cf_lmp − base_lmp`. Sort on full-precision delta before truncating to 3 and rounding for display.
- **`congestion_relieved`** — `true` iff the targeted line is **not** in `counterfactual.binding_lines` (either orientation matches). A capacity increase that still leaves the line saturated must report `false`.

## Numerical conventions

- Round monetary and flow fields to 4 decimal places in the JSON output. Sorts and comparisons use full precision before rounding.
- LMPs and MCPs are reported in `$/MWh`. Costs in `$/hour`. Flows and limits in `MW`.
- If the LP is infeasible or the solver returns a non-`optimal` status, do not fabricate values. Write a `"status": "infeasible"` field at the top level and stop.
