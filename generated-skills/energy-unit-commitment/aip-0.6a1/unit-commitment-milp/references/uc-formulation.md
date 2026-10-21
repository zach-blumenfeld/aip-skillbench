# UC MILP formulation, conventions, and debugging (what `scripts/uc_core.py` implements)

Read this when a solve or validation fails, when the input schema does not match the
field aliases, or before editing `uc_core.py`.

## Data mapping (map concepts, not names)

`load_case` looks up each concept through an alias table (`ALIASES`, `GEN_ALIASES`),
accepts resources as a dict keyed by name or a list of objects with `name`/`id`, keeps
source order, and treats IDs as opaque strings. If a new source uses other names, add
them to the alias lists instead of hard-coding a schema.

| UC concept | Field in the pglib-uc / UnitCommitment.jl JSON |
| --- | --- |
| Horizon T | `time_periods` (int); hours; report labels 1..T |
| Demand | `demand[T]` (system total, single zone) |
| Reserve requirement | `reserves[T]` (system spinning reserve) |
| Thermal set | `thermal_generators{name: {...}}` |
| Must-run | `must_run` (1 = online every period) |
| Output limits | `power_output_minimum`, `power_output_maximum` |
| Ramping | `ramp_up_limit`, `ramp_down_limit` (MW per period, above-minimum terms) |
| Startup / shutdown capability | `ramp_startup_limit`, `ramp_shutdown_limit` (max TOTAL MW in the start period / the period before a stop) |
| Minimum up/down | `time_up_minimum`, `time_down_minimum` (periods) |
| Initial conditions | `unit_on_t0`, `power_output_t0`, `time_up_t0`, `time_down_t0` |
| Startup tiers | `startup[{lag, cost}]` keyed by prior offline duration |
| Production cost | `piecewise_production[{mw, cost}]` total-cost breakpoints; first point at pmin = online minimum-output cost |
| Renewables | `renewable_generators{name: {power_output_minimum[T], power_output_maximum[T]}}`; zero cost |

Parser checks (raise or record in `parse_issues`): series length == T, finite values,
pmin <= pmax, renewable min <= max, >= 1 cost point, no repeated cost MW points,
duplicate startup lags, duplicate IDs across sets, curve span vs [pmin, pmax],
initial output consistent with initial status, time-on/off consistent with status.

## Variables (per thermal g, period t; 0-based internally)

`u` commitment (bin), `v` startup (bin), `w` shutdown (bin), `pg` output ABOVE pmin,
`r` spinning reserve, `seg_k` cost-segment fill, `d_s` startup-tier selector (bin),
`z_k` fill-order binaries only for non-convex curves; renewable output `rn`.
Actual MW = pmin*u + pg (used for reports, balance, validation). Keep conventions
separate: mixing total output with above-minimum output is the top encoding bug.

## Constraint families -> validation checks

| Model rows | Report check |
| --- | --- |
| u[t]-u[t-1] = v[t]-w[t] (u[-1]=unit_on_t0); v+w<=1 | startup_shutdown_logic |
| pg+r <= (pmax-pmin)u - max(0,pmax-SU)v[t] - max(0,pmax-SD)w[t+1] (split into two rows when min up = 1; no w[T] term at the horizon end) | reserve_deliverability, generator_limits |
| r <= RU*u (reserve only online, deployable within one ramp) | reserve_deliverability |
| pg[t]+r[t]-pg[t-1] <= RU*(u[t]-v[t]) + min(RU, SUcap-pmin)*v[t]; pg[t-1]-pg[t] <= RD*u[t] + min(RD, SDcap-pmin)*w[t]; pg[-1]=unit_on_t0*(p0-pmin) (SUcap/SDcap = min(pmax, SU/SD)) | ramping, initial_conditions |
| w[0]=0 if on at t0 and p0 > SD | initial_conditions |
| sum_{i=t-UT+1..t} v[i] <= u[t]; sum_{i=t-DT+1..t} w[i] <= 1-u[t] (windows truncated at the horizon start; post-horizon obligations not enforced unless the task says so) | minimum_up_down |
| u fixed 1 for max(0,UT-time_up_t0) periods if on at t0; fixed 0 for max(0,DT-time_down_t0) if off | initial_conditions |
| u = 1 when must_run | must_run |
| sum(pmin*u+pg) + sum rn = demand[t] | demand_balance |
| sum r >= reserves[t] (renewable headroom counts only if the task allows) | spinning_reserve |
| rmin <= rn <= rmax (rn = rmax if curtailment is not allowed) | renewable_limits |
| pg = sum seg_k; seg_k <= width_k*u; cost = C(pmin)*u + sum slope_k*seg_k | cost_consistency |
| sum_s d_s = v; d_s <= shutdowns in its offline window (tier 0 window = [1, lag_1-1], tier s = [lag_s, lag_{s+1}-1], last tier unbounded; a pre-horizon shutdown sits time_down_t0 periods before period 1) | cost_consistency |

Sign-safe encoding: write the intended inequality, then move variable terms left.
Hand check: u=1, v=1 leaves pg+r <= SU-pmin (startup capability); u=1, v=0 leaves the
normal pmax-pmin.

## Costs

Objective = sum over online periods of total cost interpolated on the curve at actual MW
+ startup cost of the tier with the largest lag <= prior offline duration (first tier if
none). Offline duration before a start = periods off since the last on period, plus
`time_down_t0` if off since t0. Do not invent no-load, reserve, curtailment, shutdown,
or ramp costs. Cost curves are cost data, not feasibility constraints.

## Solver

HiGHS through `scipy.optimize.milp` (`time_limit`, `mip_rel_gap`), in phases sharing one
`time_limit_s` budget (`FULL_MILP_SHARE`, `LNS_STEP_SHARE` in `uc_core.py`):
1. LP relaxation. It provides the fallback bound and the RINS reference. If the LP is
   infeasible, the data or the model is infeasible.
2. LP-guided start: fix every binary that is integral in the LP and solve that sub-MILP.
   This gives a first incumbent quickly.
3. Full MILP for 25% of the budget, for a valid dual bound and possibly a better incumbent.
4. Large-neighborhood search until time runs out or a full cycle finds no improvement:
   fix all binaries to the incumbent except those in a time window of T/4 periods (overlapping
   windows), then RINS (fix where incumbent and LP agree), then unit groups (units sorted
   by min up time and capacity, about 6 chunks). Each sub-MILP is a restriction of the full
   model, so its solutions are feasible for the full model and the phase-3 bound still
   bounds the gap.
Why: under a time limit, plain HiGHS lands on very different incumbents. In the container's
scipy 1.13.1 it reached 2.4% gap in 300 s on the RTS-GMLC case, while the phased search
reached about 0.6%. Newer HiGHS builds do better on their own.

Statuses:
- `optimal` when HiGHS proves it, or when the final gap against the valid bound is within
  `mip_rel_gap`.
- `time_limit_feasible` when there is an incumbent but no such proof.
- `no_incumbent` when nothing was found.
- `infeasible` when the LP or the MILP is infeasible.

`reported_mip_gap` = (best - bound) / |best|. After solving, binaries are checked to be
near-integral, then rounded and fixed, and a polish LP of the SAME model (every family)
recomputes the continuous values.

Keeping only `u` integer, or making the shutdown and tier variables continuous, gave worse
incumbents in equal time, so all transition binaries stay. Ramp rows are tightened with v/w
(same integer points, tighter LP).

## Debugging infeasibility or a failed validation

First suspect the encoding:
- total output vs output above minimum mixed up;
- startup/shutdown limits applied to the wrong quantity;
- wrong t vs t-1 index;
- over-constrained initial min up/down obligations;
- post-horizon obligations enforced when the prompt excludes them;
- cost curves treated as feasibility constraints;
- bad Big-M values;
- segment/tier variables forced when the trigger (start, online) did not occur.

Debug in stages: check shapes, relax one family at a time, add diagnostic slack variables
(e.g. on balance and reserve with a large penalty) and print the largest violations,
compare local validation with the final requirements. A repair LP is only valid if it
includes every feasibility family the report judges; always rerun validation after repair.
No incumbent at the time limit: rerun with a larger `time_limit_s` or a looser
`mip_rel_gap` before touching the model. Never write `"pass"` without validation.

## Common mistakes the scripts already guard against

Treating UC as independent hourly dispatch; counting reserve from offline units or
renewable headroom; checking reserve headroom but not startup/shutdown or ramp
deliverability; ignoring initial output in first-period ramping; ignoring time already
on/off in min up/down; losing resource order when converting dicts; treating every cost
curve as marginal cost; assuming renewable max must always be used; trusting solver
status or self-reported "pass" strings.
