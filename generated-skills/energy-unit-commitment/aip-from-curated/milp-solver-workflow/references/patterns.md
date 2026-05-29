# Patterns

Load this file from `build-variable-map`, `add-constraints-by-family`,
and `validate-independently`. It captures the three pattern families the
source skill embeds inline.

## Sign-Safe Encoding

Always write the intended inequality first, then move every variable term
to the left-hand side. The `SparseModel.add_row(terms, lo, hi)` helper
expects exactly that LHS form.

```python
# Intended: x + y <= cap * u - reduction * start
# Row form: x + y - cap*u + reduction*start <= 0
model.add_row(
    [(x, 1.0), (y, 1.0), (u, -cap), (start, reduction)],
    lo=-INF,
    hi=0.0,
)
```

Mapping the bound:
- `≤ hi`: `lo=-INF`, `hi=<value>`
- `≥ lo`: `lo=<value>`, `hi=INF`
- equality: `lo == hi`

Sanity-test non-obvious rows on a tiny hand case before scaling. For a
startup-capability row, set `u=1, start=1` and confirm the right-hand
side equals the intended startup capability; set `u=1, start=0` and
confirm normal capacity returns.

## Validation Map

Every constraint family added in `add-constraints-by-family` MUST be
mirrored by a check in `validate-independently`. The asymmetry between
"families in model" and "families in validator" is where bugs hide:

| Constraint family            | Validation check                                          | Helper in `scripts/validation_checks.py` |
|------------------------------|-----------------------------------------------------------|------------------------------------------|
| transition linking           | startup/shutdown match commitment delta; mutually exclusive | `startup_shutdown_logic_check`           |
| online capacity              | offline → zero output; online → within [pmin, pmax]       | `online_capacity_check`                  |
| joint reserve capacity       | p + r ≤ pmax * u                                           | `joint_reserve_capacity_check`           |
| ramp deliverability          | period-to-period ramp respecting start/shutdown surcharges | `ramp_check`                             |
| minimum durations            | start → forced on for min_up; shutdown → forced off for min_down | `min_up_down_check`                      |
| initial conditions           | t<need periods respect leftover up/down obligation         | `initial_conditions_check`               |
| balance equations            | Σ supply == demand per period                              | `balance_check`                          |
| reserve adequacy             | Σ scheduled reserve ≥ requirement per period               | `reserve_adequacy_check`                 |
| must-run                     | flagged generators have u==1 every period                  | `must_run_check`                         |
| renewable bounds             | 0 ≤ renewable production ≤ availability                    | `renewable_limits_check`                 |
| cost-curve logic             | recomputed objective matches reported objective            | `cost_consistency_check` + `recompute_thermal_cost` |

If the validator runs a check whose corresponding family is NOT in the
model, the solver can produce a report the validator rejects. If the
model has a family the validator skips, conversion bugs slip through to
the final report.

## Piecewise-Linear Costs

Identify the curve convention BEFORE writing variables. The same input
field name can mean different things in different cases.

Common conventions for a thermal generator cost curve:
1. **Total cost at output breakpoints** — `(p_k, C_k)` where `C_k` is the
   total $/h at output `p_k`. The first point is typically at `p_min` and
   already includes no-load cost.
2. **Marginal / incremental segment cost** — `(p_k, m_k)` where `m_k` is
   $/MWh on segment `k`. Total cost = `no_load_cost * u + Σ m_k * seg_k`.
3. **Heat-rate curve** — `(p_k, h_k)` with `h_k` in MMBtu/MWh; multiply by
   fuel price to get $/MWh.
4. **First point as no-load-like cost** — `p_k = 0`, `C_k = no_load_cost`.

For segment variables, constrain each `seg_k ∈ [0, width_k]` and
`Σ seg_k == p - p_min` (or `Σ seg_k == p` if the first segment starts at
0). Apply slopes only when the curve representation makes the slope
meaningful — never mix conventions.

`scripts/validation_checks.py::recompute_thermal_cost` assumes
convention 1 (total cost at breakpoints) with optional `no_load_cost`
and per-startup `startup_cost`. If the case uses a different convention,
either pre-convert to total-cost-at-breakpoints before calling, or
implement a parallel recompute that matches the convention exactly. Cost
mismatches between the report and the recompute are almost always
convention drift.
