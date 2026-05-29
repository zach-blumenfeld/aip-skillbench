# Modeling patterns reference

Load this when building the variable map, sparse rows, sign-safe row
encoding, or piecewise-linear cost segments. The SKILL body cites this
file at point of use; do not duplicate it inline.

## Variable map pattern

Use a `VariableMap` from `scripts/variable_map.py`. Never compute
`g * T + t` offsets by hand. The map records every block's name, shape,
bounds, and integrality, and reshapes a contiguous index range into the
shape you asked for, so callers index it as `vm["commitment"][g, t]`.

```python
from scripts.variable_map import VariableMap

vm = VariableMap()
u     = vm.alloc("commitment", (G, T), lb=0, ub=1, integer=True)
start = vm.alloc("startup",    (G, T), lb=0, ub=1, integer=True)
stop  = vm.alloc("shutdown",   (G, T), lb=0, ub=1, integer=True)
p     = vm.alloc("dispatch",   (G, T), lb=0)
r     = vm.alloc("reserve",    (G, T), lb=0)
```

Variable ownership stays obvious: type, resource, period, and any
optional segment/tier index. Cost vectors come back from
`vm.cost_vector({"dispatch": cost_per_mw, "startup": startup_cost})`,
flat incumbents come back from `vm.report_layout(result.x)` shaped like
the original blocks.

## Sparse constraint pattern

Use a `ConstraintBuilder` from `scripts/sparse_constraints.py`. For
time-expanded MILPs the row count reaches tens of thousands while each
row touches a handful of variables — a dense `A` is mostly zeros and
wastes memory.

```python
from scripts.sparse_constraints import ConstraintBuilder, INF

cb = ConstraintBuilder()

# Per-period balance: sum_g p[g, t] == demand[t]
for t in range(T):
    cb.add_row(
        [(p[g, t], 1.0) for g in range(G)],
        lo=demand[t], hi=demand[t],
        family="balance",
    )
```

Group constraints by family (`balance`, `capacity`, `ramp`, `reserve`,
`min-up-down`, `transition`, `cost-curve`, ...) so the row-label arrays
let downstream debugging report "largest violation per family" via
`scripts.sparse_constraints.largest_violations`.

Use `cb.add_rows_vectorized(...)` when the family is "for every `(g,
t)`, do X" — it accepts same-shaped index arrays and broadcasts the
coefficients across rows.

Equality vs one-sided rows:

- Equality `Ax == k`: `lo=k, hi=k`.
- Upper bound `Ax <= k`: `lo=-INF, hi=k`.
- Lower bound `Ax >= k`: `lo=k, hi=+INF`.
- Two-sided range `a <= Ax <= b`: `lo=a, hi=b`.

## Sign-safe encoding

Write the inequality in its natural form first, then move ALL variable
terms to the left-hand side. The right-hand side becomes a constant or
zero. This kills the entire class of "is it `<=` or `>=`?" sign errors.

```python
# Intended (natural form): p[g, t] + r[g, t] <= pmax[g] * u[g, t] - startup_reduction * start[g, t]
# Move every variable term to the LHS:
#   p + r - pmax * u + startup_reduction * start <= 0
# Bounds:  lo = -INF, hi = 0.

cb.add_row(
    [
        (p[g, t], 1.0),
        (r[g, t], 1.0),
        (u[g, t], -pmax[g]),
        (start[g, t], startup_reduction),
    ],
    lo=-INF,
    hi=0.0,
    family="joint-capacity",
)
```

For any non-obvious row, plug in a tiny hand case before trusting it:

- Set `u=1, start=1` and check the remaining capacity equals the
  intended startup capability.
- Set `u=1, start=0` and check normal capacity returns.

If the hand cases don't match the natural-form prose you wrote on
scratch paper, the row is wrong — fix it before assembling the matrix.

## Match model rows to validation

Keep a 1:1 mapping between each model constraint family and a
post-solve validation entry. If validation checks something the model
doesn't enforce, the solver may produce an invalid report. If the model
has a family not validated after extraction, a conversion bug can slip
through silently.

| Model family            | Validator                              |
| ----------------------- | -------------------------------------- |
| Transition linking      | `check_transitions`                    |
| Online capacity         | `check_capacity_bounds`                |
| Joint reserve capacity  | `check_reserve` (joint-capacity kind)  |
| Ramp deliverability     | `check_reserve` (ramp-deliverability)  |
| Ramp limits             | `check_ramp_limits`                    |
| Minimum durations       | `check_min_up_down`                    |
| Balance / demand        | `check_balance`                        |
| Cost-curve logic        | objective recomputer in `run_all_checks` |

## Piecewise-linear costs

Identify the curve convention BEFORE modeling. Four common shapes:

* **Total cost at output breakpoints.** Each `(mw, cost)` point is the
  full production cost when output equals `mw`. Slopes between adjacent
  points are derived; segment quantities sum to total production above
  `pmin` (or total production, depending on the convention chosen at
  parse time).
* **Marginal or incremental segment cost.** Each row gives the marginal
  cost for a segment of width `delta_mw`. Total cost is
  `sum(segment_qty * marginal_cost)`. Segment quantities must be bounded
  by their widths.
* **Heat-rate curve.** Each row gives MMBtu/MWh at a load point.
  Multiply by fuel price to get a total-cost curve, then proceed as if
  the input had always been total-cost.
* **First point as `pmin` or no-load.** Sometimes the smallest
  breakpoint represents the minimum-output cost; sometimes it represents
  a no-load cost added on top of the curve. The wrong reading
  double-counts or under-counts the online minimum.

After conversion, segment variables `s[g, t, k]` carry the *quantity*
produced in segment `k`. Constraints:

```
0 <= s[g, t, k] <= width[g, k] * u[g, t]              # segment width
sum_k s[g, t, k] == p_above_min[g, t]                 # consistency with dispatch
production_cost[g, t] = no_load * u[g, t] + sum_k slope[g, k] * s[g, t, k]
```

`p_above_min` is `p - pmin * u` when the model uses actual-MW dispatch.
When the model uses above-minimum dispatch, `p` already equals
`p_above_min`.

Do not use slopes when the data is total-cost breakpoints unless you
convert first. Do not bound segment quantities by full capacity — the
width bound is what makes the convex relaxation tight.

## Open-source solver use

Default to HiGHS via `scripts/solve_milp.py`. The helper enforces an
explicit `time_limit`, an explicit `mip_rel_gap`, and silenced output.
It raises when no incumbent is returned and otherwise hands back a
`SolveResult` dataclass with the structured fields the rest of the
workflow needs:

* `feasible` — `True` when the solver returns a feasible incumbent.
  Always re-check with independent validation regardless.
* `x` — the flat incumbent vector. Pass to `vm.report_layout(x)` to
  recover per-block arrays.
* `objective` — at the incumbent.
* `best_bound` — the solver's best dual bound when available. `None`
  otherwise. Never substitute the incumbent for the bound.
* `mip_gap` — `(obj - bound) / max(|obj|, eps)`. `None` when no bound.
  This is proof quality, not feasibility.

A time-limit hit with a feasible incumbent is usable — the validator
decides whether the incumbent is acceptable. A failure with no
incumbent is not a solution; surface the error.

## Extraction discipline

After `solve(...)` returns:

1. Verify every binary variable is near 0 or 1 with
   `scripts.variable_map.round_near_binary`. A binary that came back
   at 0.3 means the solver returned an LP relaxation, not an integer
   solution.
2. Convert internal-unit / above-minimum / segment-quantity variables
   to the report convention (usually actual MW). Do the conversion in
   one named function so the inverse path is obvious during debugging.
3. Build the report arrays with the names the prompt's schema uses.
   Preserve resource and period source ordering.
4. Run `validate_solution.run_all_checks(...)` with the closure that
   recomputes the objective from input data plus report arrays. Drift
   between solver objective and recomputed objective is the single
   loudest signal that a conversion is wrong.
5. Only after `run_all_checks(...)["ok"]` is `True` may any `"pass"`
   self-check string appear in the report.
