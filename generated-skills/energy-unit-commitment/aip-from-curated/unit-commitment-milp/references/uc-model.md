# UC model reference (scripts/solve_uc.py and scripts/validate_uc.py)

Load this when normalizing unfamiliar data, debugging an infeasible/invalid run, or extending the model.

## Canonical case schema (pglib-uc / UnitCommitment.jl JSON)

| Field | Meaning | Model use |
| --- | --- | --- |
| `time_periods` | T periods (the input horizon is authoritative) | all arrays length T |
| `demand[t]` | system load MW | equality balance |
| `reserves[t]` | spinning reserve requirement MW | `sum r >= reserves` |
| `must_run` | 1 = online every period | `u = 1` |
| `power_output_minimum/maximum` | pmin / pmax MW when online | capacity |
| `ramp_up_limit/ramp_down_limit` | MW per period, on above-minimum output | ramping |
| `ramp_startup_limit` | max total output (+reserve) in the startup period | capacity tightening |
| `ramp_shutdown_limit` | max total output (+reserve) in the period before shutdown | capacity tightening |
| `time_up_minimum/time_down_minimum` | periods on after a start / off after a stop | min up/down windows |
| `unit_on_t0`, `power_output_t0` | status and actual MW in the period before t=0 | linking, first ramp |
| `time_up_t0/time_down_t0` | periods already on / off before t=0 | initial obligations, startup tier |
| `startup[{lag,cost}]` | tier cost by prior offline duration (periods) | startup cost |
| `piecewise_production[{mw,cost}]` | TOTAL cost at output breakpoints; first point = pmin, last = pmax | production cost |
| `renewable_generators.*.power_output_minimum/maximum[t]` | per-period bounds; min == max fixes output; zero cost | bounds |

## Variables (per thermal g, period t; 0-based)

`u` on (binary), `v` startup (binary), `w` shutdown (binary), `p` output ABOVE minimum, `r` reserve,
`seg_k` cost-curve segments, `delta_s` startup tier (when > 1 tier); renewable output `pw`.
Actual MW = `pmin*u + p`; converted once at extraction. `prev` at t=0 uses `unit_on_t0` and
`unit_on_t0*(power_output_t0 - pmin)`.

## Row families and their validation checks

| Model rows (solve_uc.py) | Check (validate_uc.py) |
| --- | --- |
| `u[t] - u[t-1] = v[t] - w[t]`, `v + w <= 1` (t=0 uses unit_on_t0) | `transition_linking`: start/stop equal status changes |
| `0 <= p <= (pmax-pmin)u`, `r >= 0`, offline zeroes via `p + r <= cap*u` | `offline_zero`, `online_limits` |
| `p + r <= (pmax-pmin)u - max(pmax-RSU,0) v[t]` | `reserve_deliverability`, `startup_capability` |
| `p + r <= (pmax-pmin)u - max(pmax-RSD,0) w[t+1]` (t < T-1); `w[0]=0` if power_output_t0 > RSD; merged with the startup row when min up >= 2 | `shutdown_capability` |
| `p[t] + r[t] - p[t-1] <= RU`; `p[t-1] - p[t] <= RD` (above-minimum, first period from power_output_t0) | `ramping` |
| `sum v[t-UT+1..t] <= u[t]`; `sum w[t-DT+1..t] <= 1 - u[t]` (truncated at the horizon end) | `min_up_down` |
| on at t0: `u = 1` for first `max(0, UT - time_up_t0)`; off: `u = 0` for first `max(0, DT - time_down_t0)` | `initial_conditions` |
| `u >= must_run` | `must_run` |
| `sum(pmin u + p) + sum pw = demand` | `demand_balance` |
| `sum r (+ renewable headroom if allowed) >= reserves` | `system_reserve` |
| `pw` in `[min, max]` (or fixed at max if curtailment is forbidden) | `renewable_bounds` |
| cost = `c0*u + sum slope_k seg_k + sum cost_s delta_s` | `cost_recomputed`: curve interpolation at actual MW + tier by offline duration equals objective |

If the validator checks something the model lacks, the solver can return an invalid report; if the model has
a row the validator does not check, conversion bugs slip through. Keep the two in step when editing.

Post-horizon option (`post_horizon_min_updown`): forbids starts in the last UT-1 periods and stops in the
last DT-1 periods. Leave it off unless the prompt asks; enforcing obligations the prompt excludes is a
common source of infeasibility or extra cost.

## Startup tiers

Offline duration before a start at t = periods the unit was off immediately before t (initial history:
`time_down_t0 + t` if never started). Tier = largest lag <= duration; hottest tier if none qualifies; the
coldest tier is always allowed. Model: `v[t] = sum_s delta[s,t]`, and for every non-coldest tier
`delta[s,t] <= sum of w[t-d]` over d in [lag_s (1 for the hottest), lag_{s+1}-1], plus 1 when the unit was
off at t0 and `time_down_t0 + t` falls in that window. Tier costs normally rise with lag, so the
solver picks the hottest allowed tier.

## Production cost

Total-cost breakpoints: online cost = cost at pmin (`c0*u`) + segment slopes times segment MW, widths
bounded by `width*u`. Convex curves need no extra binaries; non-convex ones get ordering binaries (the
script adds them automatically). If a source gives marginal/incremental segment costs or heat rates,
convert to total cost at breakpoints first. Use only components present in the data; no invented
no-load, reserve, curtailment, shutdown, or ramping costs.

## MILP implementation patterns (for extensions)

- Deterministic variable map: `idx = m.alloc((G, T), lb, ub, integer, cost)` returns an index array;
  never scatter index arithmetic.
- Sparse rows: `m.add_row([(col, coef), ...], lo, hi)`; equality rows for conservation/linking, one-sided
  rows for capacity, reserve, ramping, timing, logic.
- Sign-safe encoding: write the intended inequality first, then move variable terms left. Example:
  intended `x + y <= cap*u - reduction*start` becomes row `x + y - cap*u + reduction*start <= 0`. Hand-test
  non-obvious rows: `u=1,start=1` leaves the startup capability; `u=1,start=0` restores normal capacity.
- Add constraints family by family (bounds, linking, balance, time coupling, capacity/ramp, cost logic)
  and add the matching validator check in the same edit.
- Extensions: zonal balance = one balance row per zone plus line-flow variables bounded by limits; storage =
  state-of-charge equality rows with charge/discharge efficiency; extra reserve products = one requirement
  row each plus a joint capability row. Keep extensions only if the data/prompt requires them.

## Solver use (HiGHS via scipy.optimize.milp)

`milp(c, integrality, bounds=Bounds(lb, ub), constraints=LinearConstraint(A, lo, hi),
options={"time_limit": s, "mip_rel_gap": g, "disp": False})`. Status 0 = optimal within gap;
1 = time/iteration limit (usable if `res.x` exists); 2 = infeasible; `res.x is None` = no incumbent, not a
solution. `res.mip_gap` / `res.mip_dual_bound` give the proof quality; report them separately from
feasibility. Binaries are rounded only when within 1e-4 of 0/1 (`max_binary_deviation`). On the RTS-GMLC
73-unit, 48-period case the container HiGHS reaches 1% in ~10 s; tighter gaps use the full time limit and
return a better incumbent.

## Debugging infeasibility

First suspect the encoding: total output mixed with output above minimum; startup/shutdown limits applied
to the wrong quantity; `t` vs `t-1`; over-constrained initial min up/down; post-horizon obligations the
prompt excludes; cost curves treated as feasibility constraints; bad Big-M; segment/tier variables forced
when no start happened. Debug in stages: check shapes, relax one family at a time, add diagnostic slack,
print the largest violations, compare local validation with the task's final requirements.
