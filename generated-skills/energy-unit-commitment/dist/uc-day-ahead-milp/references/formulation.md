# MILP formulation used by `scripts/uc_milp.py`

Load this when debugging infeasibility, a validation failure, or when you must extend the model
(e.g. a prompt adds a rule the script does not cover). Indices: unit g, period t (0-based
internally, 1-based in reports). `p` = output above minimum, `cap = pmax - pmin`.

## Variables (per g, t)

| var | type | meaning |
| --- | --- | --- |
| `u` | binary | online |
| `v`, `w` | binary | startup, shutdown transition |
| `p` | [0, cap] | output above minimum; actual MW = `pmin*u + p` |
| `r` | [0, cap] | spinning reserve |
| `seg_k` | [0, width_k] | production-cost segment k of the total-cost curve |
| `delta_s` | binary | startup in tier s (only when the unit has > 1 tier) |
| `q` (per renewable, t) | [min, max] | renewable output (`[max, max]` with `--no-curtail`) |

Objective: `Σ cost(pmin)*u + Σ slope_k*seg_k + Σ tier_cost_s*delta_s` (single-tier units: `cost*v`).
Nothing else: no reserve, curtailment, shutdown, or ramp cost unless the data provides it.

## Constraint families → validation families

Write the intended inequality first, then move variable terms left (sign-safe encoding).

| family | rows | validation key |
| --- | --- | --- |
| transition linking | `u[t] - u[t-1] = v[t] - w[t]` (t=0 uses `unit_on_t0`); `v + w <= 1` | `startup_shutdown_logic` |
| min up | `Σ_{k=t-UT+1..t} v[k] <= u[t]` (window clipped at 0) | `minimum_up_down` |
| min down | `Σ_{k=t-DT+1..t} w[k] <= 1 - u[t]` | `minimum_up_down` |
| initial obligations | `u=1` for `min(T, max(0,UT-time_up_t0))` periods if on at t0; `u=0` for `min(T, max(0,DT-time_down_t0))` periods if off | `initial_conditions` |
| must-run | `u = 1` all t | `must_run` |
| joint capability (UT>1, t<T-1) | `p + r <= cap*u - max(0,pmax-RSU)*v[t] - max(0,pmax-RSD)*w[t+1]` | `reserve_deliverability`, `generator_limits` |
| joint capability (UT=1 or last t) | the same two reductions in **separate** rows (a UT=1 unit may start at t and stop at t+1; the combined row would wrongly forbid it) | same |
| ramp up | `p[t] + r[t] - p[t-1] <= RU`; t=0 uses `(power_output_t0 - pmin)*unit_on_t0` | `ramping` / `initial_conditions`, `reserve_deliverability` |
| ramp down | `p[t-1] - p[t] <= RD`; t=0 likewise | `ramping` / `initial_conditions` |
| shutdown at t0 | `(P0-pmin)*on0 <= cap*on0 - max(0,pmax-RSD)*w[0]` | `initial_conditions` |
| cost curve | `p = Σ seg_k`, `seg_k <= width_k*u` (convex); nonconvex adds ordered binaries `z_k` | `cost_consistency` |
| startup tiers | `v = Σ delta_s`; for s < last: `delta_s[t] = 0` for 1-based t in `[max(1, lag_{s+1}-time_down_t0+1), lag_{s+1}-1]`; for t ≥ lag_{s+1}: `delta_s[t] <= Σ_{i=lag_s..lag_{s+1}-1} w[t-i]` | `cost_consistency` |
| balance | `Σ(pmin*u + p) + Σ q = demand[t]` | `demand_balance` |
| reserve | `Σ r >= reserves[t]` (thermal online units only) | `spinning_reserve` |
| renewable bounds | variable bounds | `renewable_limits` |

The validator (`validate`) re-derives every family from the report arrays and the input only,
so a conversion bug between model and report is caught. Anything validated must be modelled and
vice versa; if you add a rule to one, add it to the other.

Hand-check of the startup row: with `u=1, v=1` the remaining capability is
`cap - (pmax - RSU) = RSU - pmin`, i.e. total output + reserve ≤ RSU; with `v=0` the full `cap`
returns. When RSU = pmin (common), a unit produces exactly pmin and carries zero reserve in its
startup period, and likewise in the period before it shuts down.

Ramping applies to above-minimum output, so the jump from 0 to pmin at startup is governed by the
startup limit, not the ramp rate. Minimum up/down windows are clipped at the horizon end
(a unit started in the last hours must stay on until T; nothing beyond T is representable).

## Solver use (HiGHS via `scipy.optimize.milp`)

- Deterministic variable map: one allocation function, ownership (type, unit, period, segment/tier)
  obvious; sparse COO rows; equality rows for linking/balance, one-sided rows for limits.
- Status: scipy 0 → `optimal` (within `mip_rel_gap`); 1 (time/iteration limit) with an incumbent →
  `time_limit_feasible`; no `x` → no solution, never report it.
- Gap: `res.mip_gap` (fallback: from `res.mip_dual_bound`); `null` if neither is reliable.
  Feasibility and proof quality are separate: a feasible schedule with a large gap is still feasible.
- Binaries are rounded only if within 1e-4 of 0/1; startup/shutdown are re-derived from the rounded
  commitment; continuous values are clipped to their bounds (noise ~1e-9).
- The reported `objective_cost` is recomputed from the extracted arrays (curve interpolation at
  actual MW + tier cost from offline duration) and cross-checked against the solver objective.

## Debugging infeasibility (no incumbent, or validation FAIL)

Suspect the encoding first:
- mixing total output with output above minimum (ramps, reserve, cost, report);
- startup/shutdown limits applied to the wrong quantity or wrong `t` / `t+1` / `t-1` index;
- over-constraining initial minimum up/down (use `UT - time_up_t0`, not `UT`);
- enforcing post-horizon obligations the prompt excludes;
- treating a cost curve as a feasibility constraint (curve must only price output);
- bad Big-M values; requiring segment/tier variables when the trigger did not occur;
- initial ramp-down: an on unit with `P0 - pmin > RD` cannot drop to pmin (or shut down) in period 1.

Debug in stages: check array shapes; relax one family at a time; add a priced slack to balance
and reserve to see where the shortfall is; print the largest violations; compare the script's
validation with the task's stated requirements. A fixed-commitment repair LP is acceptable only if
it contains every family above (including transition-dependent ramp, reserve, startup, shutdown,
minimum-duration); rerun `validate` after any repair.
