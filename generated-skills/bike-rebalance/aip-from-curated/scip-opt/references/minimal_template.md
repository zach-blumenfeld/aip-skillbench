# Minimal PySCIPOpt Model Template

Copy-and-adapt skeleton for a fresh optimization model. Mirrors the
curated SKILL.md template line-for-line — same variable names, same
constraint shape, same default limits, same status / incumbent check.
Use it as the spine; layer the patterns from `patterns.md` and the
reproducibility helper from `scripts/set_reproducibility.py` onto it.

```python
from pyscipopt import Model, quicksum

model = Model("optimization_model")
model.hideOutput()

I = range(n_items)

# Decision variables — binary "use it" plus the integer quantity it gates
# and a slack for absolute-deviation penalty.
x = {i: model.addVar(vtype="B", name=f"x_{i}") for i in I}
amount = {
    i: model.addVar(vtype="I", lb=0, ub=capacity[i], name=f"amount_{i}")
    for i in I
}
dev = {i: model.addVar(lb=0, name=f"dev_{i}") for i in I}

for i in I:
    # binary activation — only allow amount when x is on
    model.addCons(amount[i] <= capacity[i] * x[i])
    # absolute-deviation linearization — never write abs() on SCIP exprs
    model.addCons(amount[i] - target[i] <= dev[i])
    model.addCons(target[i] - amount[i] <= dev[i])

# Single objective with named components (helps debugging and validation).
cost = quicksum(fixed_cost[i] * x[i] for i in I)
penalty = penalty_weight * quicksum(dev[i] for i in I)
model.setObjective(cost + penalty, "minimize")

# Default limits — 5 min wall clock, 1% MIP gap.
model.setParam("limits/time", 300.0)
model.setParam("limits/gap", 0.01)

model.optimize()

status = str(model.getStatus()).lower()
if model.getNSols() == 0:
    raise RuntimeError(f"SCIP found no feasible solution; status={status}")

objective = float(model.getObjVal())
selected = [i for i in I if model.getVal(x[i]) > 0.5]
```

After this point, **always** independently reconstruct each named
objective component (`cost`, `penalty`) from the extracted variable
values and assert it matches `model.getObjVal()` — use
`scripts/solve_helpers.assert_objective_component`. Solver feasibility
is not a substitute for problem-level validation.
