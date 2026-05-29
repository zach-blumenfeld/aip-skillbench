# Minimal PySCIPOpt Template

Use this as a scaffold when starting a new model. Replace the placeholder sets,
costs, and constraint shapes with the problem-specific equivalents.

```python
from pyscipopt import Model, quicksum

model = Model("optimization_model")
model.hideOutput()

I = range(n_items)

# Binary choice: include item i?
x = {i: model.addVar(vtype="B", name=f"x_{i}") for i in I}

# Integer quantity allowed only when x[i] is on (bounded by capacity[i]).
amount = {
    i: model.addVar(vtype="I", lb=0, ub=capacity[i], name=f"amount_{i}")
    for i in I
}

# Non-negative slack for absolute-deviation penalty against target[i].
dev = {i: model.addVar(lb=0, name=f"dev_{i}") for i in I}

for i in I:
    # Linking: quantity cannot exceed capacity unless the option is selected.
    model.addCons(amount[i] <= capacity[i] * x[i])
    # Linearised |amount[i] - target[i]| <= dev[i].
    model.addCons(amount[i] - target[i] <= dev[i])
    model.addCons(target[i] - amount[i] <= dev[i])

cost = quicksum(fixed_cost[i] * x[i] for i in I)
penalty = penalty_weight * quicksum(dev[i] for i in I)
model.setObjective(cost + penalty, "minimize")

model.setParam("limits/time", 300.0)
model.setParam("limits/gap", 0.01)
model.optimize()

status = str(model.getStatus()).lower()
if model.getNSols() == 0:
    raise RuntimeError(f"SCIP found no feasible solution; status={status}")

objective = float(model.getObjVal())
selected = [i for i in I if model.getVal(x[i]) > 0.5]
```

## Notes

- `model.hideOutput()` suppresses solver chatter; remove while debugging.
- Always require `model.getNSols() > 0` before reading variable values —
  a non-zero status is not enough on its own.
- `model.getVal(var)` returns floats even for binary/integer variables. Compare
  binaries against `0.5`, round integers as needed.
- Combine this template with `scripts/configure_reproducibility.py` whenever
  repeatable runs matter (benchmarks, regression tests, oracle comparisons).
