# UC Constraint Families — Reference Formulations

Load this when working out the model in `formulate-uc-model`. These are the
canonical patterns the curated operating rules called out, written as
copy-paste-ready pseudocode. The `validate_schedule.py` script enforces
every one of these checks on the final report.

## Variable Conventions — Keep Separate

```
u[g, t]      # commitment / on status, binary
v[g, t]      # startup transition, binary  (curated source: start)
w[g, t]      # shutdown transition, binary (curated source: stop)
p[g, t]      # production (actual MW OR above-minimum MW; pick one)
r[g, t]      # scheduled spinning reserve, continuous, >= 0
```

Conversions:

```
actual_output = pmin[g] * u[g, t] + p_above_min[g, t]
p_above_min   = actual_output - pmin[g] * u[g, t]
```

Reports demand actual MW. Internal solvers often use above-min for tighter
formulations. Whichever you pick, do not mix conventions in ramping, reserve,
cost, or reporting.

## Transition Logic

```
prev_u = unit_on_t0[g] if t == 0 else u[g, t - 1]
u[g, t] - prev_u == v[g, t] - w[g, t]
v[g, t] + w[g, t] <= 1
```

Validation form (mirrors `_recompute_transition_indicators` in the grader):

```
prev_on = unit_on_t0[g]
for t in range(T):
    assert v[g, t] == max(u[g, t] - prev_on, 0)
    assert w[g, t] == max(prev_on - u[g, t], 0)
    prev_on = u[g, t]
```

## Capacity And Offline-Zero

Actual-MW form:

```
pmin[g] * u[g, t] <= production[g, t] <= pmax[g] * u[g, t]
r[g, t] >= 0
when u[g, t] == 0: production == 0 and r == 0
```

Above-minimum form (let `cap = pmax - pmin`):

```
0 <= p_above_min[g, t] <= cap * u[g, t]
r[g, t] >= 0
```

## Reserve Deliverability (joint cap, NOT headroom-only)

```
startup_reduction   = max(pmax - ramp_startup_limit, 0)
shutdown_reduction  = max(pmax - ramp_shutdown_limit, 0)

p_above_min[g, t] + r[g, t] <= cap * u[g, t]
                              - startup_reduction * v[g, t]

# Pre-shutdown capability, applied at t for t+1 shutdown indicator:
if t < T - 1:
    p_above_min[g, t] + r[g, t] <= cap * u[g, t]
                                  - shutdown_reduction * w[g, t + 1]
```

Headroom-only checks (`r <= pmax - production`, `r <= ramp_up`) are not
sufficient: production and reserve compete for the same physical
capability, and startup/pre-shutdown periods truncate available envelope.

## Ramping (with reserve on the up side; initial p0 matters)

```
p0_above_min = unit_on_t0[g] * (power_output_t0[g] - pmin[g])
previous     = p0_above_min if t == 0 else p_above_min[g, t - 1]

p_above_min[g, t] + r[g, t] - previous <= ramp_up_limit[g]
previous - p_above_min[g, t]           <= ramp_down_limit[g]
```

If your model uses actual production rather than above-min, convert
consistently before applying these checks.

## Minimum Up / Down

Initial-condition obligation windows:

```
if unit_on_t0[g] == 1 and time_up_t0[g] < time_up_minimum[g]:
    remaining = min(T, time_up_minimum[g] - time_up_t0[g])
    u[g, 0:remaining] == 1

if unit_on_t0[g] == 0 and time_down_t0[g] < time_down_minimum[g]:
    remaining = min(T, time_down_minimum[g] - time_down_t0[g])
    u[g, 0:remaining] == 0
```

In-horizon obligations after each transition:

```
if v[g, t] == 1:
    for tau in range(t, min(T, t + time_up_minimum[g])):
        u[g, tau] == 1

if w[g, t] == 1:
    for tau in range(t, min(T, t + time_down_minimum[g])):
        u[g, tau] == 0
```

Follow the prompt on whether post-horizon obligations are enforced; pglib-uc
defaults to clipping at T.

## Startup Costs (lag-indexed tiers)

```
def startup_cost_for_duration(tiers, offline_duration):
    tiers = sorted(tiers, key=lambda z: z["lag"])
    chosen = tiers[0]["cost"]
    for tier in tiers:
        if tier["lag"] <= offline_duration:
            chosen = tier["cost"]
        else:
            break
    return chosen
```

`offline_duration` is the count of consecutive offline periods immediately
preceding the startup. Initialize from `time_down_t0` when `unit_on_t0 == 0`.
Reset to 0 the period the unit is online; increment by 1 each offline period.

## Piecewise Production Cost (total cost at actual MW)

```
def total_cost_from_curve(points, output_mw):
    pts = sorted((p["mw"], p["cost"]) for p in points)
    if output_mw <= pts[0][0]:
        return pts[0][1]
    if output_mw >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= output_mw <= x1:
            return y0 + (output_mw - x0) * (y1 - y0) / (x1 - x0)
    raise ValueError("output outside curve")
```

The first point's cost typically represents online minimum-output cost
(equivalent to a no-load + production floor). DO NOT add a separate no-load
cost on top unless the data has one as an explicit field.

## System Balance (single-zone)

```
sum_g actual_thermal[g, t] + sum_i renewable_output[i, t] == demand[t]   (within tol)
sum_g r[g, t] >= reserves[t]                                              (within tol)
```

Renewables:

```
power_output_minimum[i, t] <= renewable_output[i, t] <= power_output_maximum[i, t]
```

If `pmin == pmax`, the renewable is fixed; do not curtail it. Do not count
renewable headroom as spinning reserve unless the prompt explicitly allows it.

## Must-Run

```
if must_run[g] == 1:
    u[g, t] == 1 for all t
```

## Tolerances (mirrored from the grader)

| symbol                  | value | applies to                                  |
|-------------------------|-------|---------------------------------------------|
| TOL_POWER_BALANCE_MW    | 1e-2  | demand balance, hourly thermal/renewable    |
| TOL_RESERVE_MW          | 1e-2  | system reserve, scheduled spinning reserve  |
| TOL_GENERATOR_MW        | 1e-3  | per-generator output, renewable bounds      |
| TOL_RAMP_MW             | 1e-3  | ramping inequalities                        |
| TOL_BINARY              | 1e-5  | rounding 0/1 from solver                    |
| TOL_COST_REL            | 1e-4  | relative cost match                         |
| TOL_COST_ABS            | 1e-2  | absolute cost floor                         |
