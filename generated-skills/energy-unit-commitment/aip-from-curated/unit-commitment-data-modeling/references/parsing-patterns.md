# Parsing patterns reference

Load this when inspecting unstructured UC input data and you need the
concept map, shape vocabulary, and production-convention rules. The
SKILL body cites this file at point of use; do not duplicate it inline.

## Concept aliases — map by meaning, not by name

Different sources name the same concept differently. Match on units,
shape, and context, not on a hard-coded field name. When a source
field is ambiguous, treat the prompt and schema as authoritative.

| UC concept            | Common source names                                            |
| --------------------- | -------------------------------------------------------------- |
| Horizon               | periods, hours, timestamps, interval count                     |
| Demand                | load, system demand, net load, zone load                       |
| Reserve requirement   | spinning, operating, contingency, regulation reserve            |
| Resource sets         | thermal, renewable, storage, import/export                     |
| Commitment status     | on/off, online, active, unit status                            |
| Output limits         | minimum stable output, maximum output, availability            |
| Ramping               | ramp up/down, startup capability, shutdown capability          |
| Minimum up/down       | required duration after start/stop                              |
| Initial conditions    | initial status, initial output, time already on/off            |
| Must-run              | forced online, fixed status                                    |
| Startup data          | fixed costs or tiers by prior offline duration                 |
| Production cost       | linear coefficients, heat rate, piecewise or total-cost curves |
| Renewable availability| hourly min/max output or forecast bounds                       |

## Common data shapes

Five shapes cover most UC source data:

* **Scalar by resource** — `pmin`, `pmax`, `min_up`, `min_down`, ramp
  rates, startup ramp, must-run.
* **Time series by system or zone** — demand, reserve requirement.
* **Time series by resource** — renewable availability, planned outage
  status.
* **Curve/tier tables** — startup costs keyed by prior offline lag;
  production cost as breakpoints, segments, or heat-rate rows.
* **Nested resource objects** — generator-specific limits, status,
  and costs grouped under one resource record.

## Normalized `case` representation

After mapping source fields to UC concepts, project them into a small
uniform shape so downstream model construction code does not need to
know the source format:

```python
case = {
    "T": T,                              # horizon length
    "periods": periods,                  # length T, source labels
    "thermal_names": thermal_names,      # length G, source order
    "renewable_names": renewable_names,  # length R, source order
    "demand": demand,                    # shape (T,)
    "reserve_requirement": reserve,      # shape (T,)
    "thermal": {                         # per-unit, keyed by name
        "<g>": {
            "pmin": float, "pmax": float,
            "ramp_up": float, "ramp_down": float,
            "min_up": int, "min_down": int,
            "initial_on": 0 | 1,
            "initial_on_duration": int,
            "initial_off_duration": int,
            "initial_output": float,
            "must_run": [int, ...],      # optional periods
            "production_curve": [{"mw": float, "cost": float}, ...],
            "startup_tiers":    [{"lag": int, "cost": float}, ...],
        }, ...
    },
    "renewable": {                       # per-resource, keyed by name
        "<r>": {
            "min": [float, ...],         # length T
            "max": [float, ...],         # length T
        }, ...
    },
}
```

Use this exact shape as the input to `scripts/parser_checks.py`.

## Time, ordering, and units

* The prompt's horizon is authoritative. Preserve source period order.
* Keep zero-based internal indexes separate from one-based or
  timestamped report labels.
* Verify every time series has length `T`. The bundled checker does
  this; do not rely on numpy broadcasting to silently pad.
* Preserve resource order unless the prompt explicitly requires
  sorting. Reports often expect source order.
* Treat resource IDs as opaque strings. Do not parse them for meaning.
* Keep thermal and renewable sets separate when their constraints
  differ — joining them early is a frequent source of bugs.
* Check power units (MW vs kW), period duration (hour vs sub-hour),
  ramp-rate units (MW/period vs MW/hour vs % of capacity), and cost
  units before converting anything. Convert once, at the boundary.

## Production convention — pick one, lock it

Many UC models carry production internally as output above minimum:

```
output_above_min[g, t] = actual_output[g, t] - pmin[g] * commitment[g, t]
actual_output[g, t]     = pmin[g] * commitment[g, t] + output_above_min[g, t]
```

Reports usually require actual MW; the model may use either internally.
Pick one convention for the whole model and convert ONLY at extraction
time. Ramping, reserve deliverability, and the cost curve must all be
expressed in the same convention used internally — mixing conventions
inside the same model is a frequent source of off-by-`pmin` bugs.

## Startup tiers

Tiers describe how startup cost grows with prior offline duration.
`scripts/startup_tier.py` implements the lookup; the rule is "largest
`lag` not exceeding the prior offline duration wins". Two consequences
worth keeping in mind when reading source data:

* Tier lists may arrive unsorted; do not assume monotone order.
* Prior offline duration must be consistent with `initial_on`,
  `initial_off_duration`, and the chosen production convention. If the
  unit started offline pre-horizon, `initial_off_duration` is the
  starting value of the offline counter.

## Production cost curves

Identify the shape of cost data before committing to an internal
representation:

* **Total cost at breakpoints.** Use `scripts/cost_curve.py` directly;
  it interpolates linearly between breakpoints and clamps at the
  endpoints.
* **Marginal or incremental segment costs.** Integrate to total cost
  before storing. Do not feed marginal data to `cost_curve.py`.
* **Heat-rate tables.** Multiply by fuel price and add any
  no-load/fixed cost the source provides to get total cost; then store
  as breakpoints.
* **Linear coefficient pairs (a + b * P).** Evaluate at endpoints (and
  any internal breakpoints) and store as a two-point breakpoint list.

If the smallest breakpoint sits at `pmin`, its cost may already cover
the online minimum-output cost; do not invent an additional no-load
cost. If the source explicitly provides a separate no-load or fixed
online cost, add it as a separate per-period term — never fold it into
the breakpoint cost silently.

## Renewables

* Parse hourly minimum and maximum output as `(R, T)` shapes.
* `min[t] == max[t]` means output is fixed in period `t`; the model
  has no choice for that resource in that period.
* When curtailment is allowed, output may sit anywhere in
  `[min[t], max[t]]`.
* Do not count renewable headroom (`max - output`) as spinning reserve
  unless the prompt explicitly allows it.
* Renewable production cost is zero unless the source data says
  otherwise.
