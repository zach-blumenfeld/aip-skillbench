# Objective assembly

Build the objective from **named components**, each a single `quicksum`
expression. Keep the components reachable as separate Python expressions
even after `setObjective` — the validator recomputes each one independently
from the extracted solution.

## Canonical pattern

```python
travel_cost  = quicksum(distance[i, j] * x[v, i, j] for v in vehicles for i, j in arcs)
fixed_cost   = quicksum(vehicle_fixed_cost[v] * use_vehicle[v] for v in vehicles)
penalty_cost = quicksum(penalty[i] * unmet[i] for i in customers)

model.setObjective(travel_cost + fixed_cost + penalty_cost, "minimize")
```

## Naming components

Pick names from the problem statement, not generic labels. A reviewer
should be able to map every component back to a rule:

- `travel_cost` — sum over arcs of distance × arc binary.
- `labor_cost` — sum over assignments of hourly rate × hours.
- `inventory_holding_cost` — sum over (location, period) of holding rate ×
  inventory level.
- `unmet_demand_penalty` — sum over customers of penalty weight × unmet.
- `overtime_penalty` — sum over (worker, shift) of overtime cost × overtime
  hours.
- `setup_cost` — sum over (job, machine) of fixed cost × setup binary.

## What goes in the objective vs the constraints

- **Hard rules** (cannot be violated) → constraint, not objective.
- **Soft targets** (allowed to miss with a cost) → nonnegative slack +
  penalty term in the objective.
- **Operational preferences** (minor) → small coefficient in the objective.
  Keep penalty weights well-separated from primary cost components so the
  solver does not trade real cost for tiny preference improvements.

## Worked: rebalance objective

```python
travel_cost   = quicksum(distance[i, j] * x[v, i, j] for v in vehicles for i, j in arcs)
unmet_penalty = penalty_weight * quicksum(unmet[i] for i in stations)

model.setObjective(travel_cost + unmet_penalty, "minimize")
```

After solving, the report should expose both numbers as separate fields, and
the validator should recompute them from the extracted routes and station
net-change values.

## Common mistakes

- **Squashing components into one expression.** Loses the ability to
  validate each piece independently.
- **Penalty weight too small.** The solver ignores soft targets entirely.
  Pick a weight at least as large as the marginal cost of meeting them
  through the cheapest hard mechanism, otherwise the soft term is decorative.
- **Penalty weight too large.** The solver tightens soft targets at the
  expense of real cost; the objective becomes dominated by slack and
  ignores trade-offs the problem intended.
- **Forgetting that maximization changes signs.** If using `"maximize"`,
  penalties subtract rather than add. The library convention here is to
  minimize cost + penalty.
