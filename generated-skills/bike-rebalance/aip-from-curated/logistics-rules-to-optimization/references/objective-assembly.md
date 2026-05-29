# Objective Assembly

Build the objective from named components so each cost or penalty term stays interpretable, auditable, and easy to weight independently.

```python
travel_cost = quicksum(distance[i, j] * x[v, i, j] for v in vehicles for i, j in arcs)
fixed_cost = quicksum(vehicle_fixed_cost[v] * use_vehicle[v] for v in vehicles)
penalty_cost = quicksum(penalty[i] * unmet[i] for i in customers)

model.setObjective(travel_cost + fixed_cost + penalty_cost, "minimize")
```

Typical named components seen across logistics problems:

- `travel_cost` — distance × arc binaries, summed over vehicles and arcs.
- `fixed_cost` — vehicle/facility fixed cost × use binary.
- `labor_cost` — labor rate × time variables.
- `inventory_penalty` — holding/shortage penalty × inventory or slack variables.
- `unmet_demand_penalty` — penalty × slack on demand satisfaction.

Keep components named in the code so the agent can recompute each contribution from the solved variable values during the independent validation step.
