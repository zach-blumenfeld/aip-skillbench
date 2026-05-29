# Constraint pattern reference

Load this when constructing the optimization model or a heuristic schedule
and you need the exact algebraic form of each operating constraint.

The patterns below assume the per-unit, per-period variables introduced
in the SKILL body:

```
u[g, t]      # commitment, binary
start[g, t]  # startup transition, binary
stop[g, t]   # shutdown transition, binary
p[g, t]      # production (actual MW OR above-minimum MW — pick one)
r[g, t]      # scheduled spinning reserve
```

## Production conventions

Two conventions; do not mix them inside the same model.

**Actual MW.** `p[g, t]` is the unit's actual output.

```
pmin[g] * u[g, t] <= p[g, t] <= pmax[g] * u[g, t]
```

**Above-minimum MW.** `p_above_min[g, t] = p[g, t] - pmin[g] * u[g, t]`.

```
cap[g] = pmax[g] - pmin[g]
0 <= p_above_min[g, t] <= cap[g] * u[g, t]
```

When the report demands actual MW, convert at extraction time. Reserve
deliverability, ramping, and the cost curve must all be expressed in the
same convention used internally.

## Offline zeros

If `u[g, t] == 0`, both production and reserve must be zero. The
capacity bounds above enforce production = 0; add `reserve <= M * u`
(or `reserve <= pmax * u`) to enforce reserve = 0 jointly.

## Transition logic

Link `start`, `stop`, and `u` to one another and to the initial state.

```
prev_u = initial_on[g] if t == 0 else u[g, t-1]
u[g, t] - prev_u == start[g, t] - stop[g, t]
start[g, t] + stop[g, t] <= 1
```

Validation equivalent (read-only check, no optimization):

```python
prev_on = initial_on[g]
for t in range(T):
    assert start[g, t] == int(u[g, t] == 1 and prev_on == 0)
    assert stop[g, t]  == int(u[g, t] == 0 and prev_on == 1)
    prev_on = u[g, t]
```

## Reserve deliverability

Headroom-only checks (`reserve <= pmax - production`, `reserve <= ramp_up`)
are necessary but not sufficient. Use joint capacity with `u`, and apply
startup-period tightening if the data carries `startup_limit[g]`.

Actual-MW convention:

```
p[g, t] + r[g, t] <= pmax[g] * u[g, t]
if start[g, t] == 1:
    p[g, t] + r[g, t] <= startup_limit[g]
```

Above-minimum convention with a linear startup model:

```
startup_reduction = max(pmax[g] - startup_limit[g], 0.0)
p_above_min[g, t] + r[g, t] <= cap[g] * u[g, t] - startup_reduction * start[g, t]
```

Apply analogous shutdown-period or pre-shutdown capability rules when the
data and prompt require them.

## Ramping

Ramping is across periods, so use the unit's pre-horizon output for `t = 0`.
Apply ramp-up to production-plus-reserve so reserve is physically
deployable on the next period.

```
previous = initial_above_min[g] if t == 0 else p_above_min[g, t-1]
p_above_min[g, t] + r[g, t] - previous <= ramp_up[g]
previous - p_above_min[g, t] <= ramp_down[g]
```

If the model uses actual production, convert to above-minimum before
applying these inequalities (subtract `pmin * u`). Re-check ramping
after any dispatch repair or post-processing step.

## Minimum up/down time

`min_up[g]` and `min_down[g]` are time-window constraints triggered by
`start` and `stop`. They must also account for the pre-horizon time the
unit has already been on or off.

Within-horizon validation:

```python
if start[g, t] == 1:
    for tau in range(t, min(T, t + min_up[g])):
        assert u[g, tau] == 1
if stop[g, t] == 1:
    for tau in range(t, min(T, t + min_down[g])):
        assert u[g, tau] == 0
```

Pre-horizon carryover:

```
if initial_on[g] == 1 and initial_on_duration[g] < min_up[g]:
    u[g, t] must remain 1 for the first (min_up - initial_on_duration) periods.
if initial_on[g] == 0 and initial_off_duration[g] < min_down[g]:
    u[g, t] must remain 0 for the first (min_down - initial_off_duration) periods.
```

Follow the prompt on whether post-horizon obligations (a start near the
end of the horizon committing future periods) are enforced.

## Demand balance and system reserve

Single-zone system, actual-MW thermal:

```
sum_g actual_thermal[g, t] + sum_r renewable_output[r, t] == demand[t]
sum_g reserve[g, t] >= reserve_requirement[t]
```

Multi-zone or networked systems substitute the prompt's nodal/zonal
balance. Reserve requirements may also be zonal — read the prompt
carefully.

## Renewable bounds

```
renewable_min[r, t] <= renewable_output[r, t] <= renewable_max[r, t]
```

If `min == max`, the output is fixed (no curtailment). If `min < max`,
curtailment is allowed. Do not count renewable headroom (`max - output`)
as spinning reserve unless the prompt explicitly allows it.

## Startup costs

Tier-based: each tier is `{"lag": L, "cost": C}` — "if offline at least
`L` periods, cost is at least `C`". Apply the LARGEST `lag` not exceeding
the offline duration immediately before the startup. Pre-horizon offline
duration is `initial_off_duration[g]`.

The applied lookup lives in `scripts/startup_cost.py` —
`choose_startup_cost(tiers, offline_duration)` and
`schedule_startup_cost(u, start, tiers, initial_on, initial_off_duration)`.

## Production costs

Production costs come from a piecewise-linear total-cost curve of
`{"mw": x, "cost": y}` breakpoints. The cost at each breakpoint is the
TOTAL cost at that output, not a marginal rate. Interpolate linearly
between adjacent breakpoints; clamp to the endpoint cost outside the
curve.

The smallest breakpoint is typically at `pmin`; its cost may include the
online minimum-output cost. Do not add a separate fixed online cost
unless the data explicitly says so. Offline periods contribute zero.

Use `scripts/production_cost.py` —
`total_cost_from_curve(points, output_mw)` and
`schedule_production_cost(u, production_actual_mw, points)`.
