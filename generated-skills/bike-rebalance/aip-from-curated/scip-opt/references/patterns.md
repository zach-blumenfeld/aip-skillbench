# Common PySCIPOpt Modeling Patterns

Load this file when you need a worked snippet for one of the modeling
constructs below. Each section is self-contained and can be pasted into a
larger model after adapting names.

## Binary activation

Allow a quantity only when an option is active.

```python
use = {i: model.addVar(vtype="B", name=f"use_{i}") for i in I}
q = {i: model.addVar(lb=0, ub=upper[i], name=f"q_{i}") for i in I}

for i in I:
    model.addCons(q[i] <= upper[i] * use[i])
```

The big-M coefficient `upper[i]` keeps the linking tight; never use an
arbitrarily large constant when a real upper bound is available.

## Assignment

Assign each item to exactly one option, respecting option capacity.

```python
assign = {
    (i, j): model.addVar(vtype="B", name=f"assign_{i}_{j}")
    for i in items
    for j in options
}

for i in items:
    model.addCons(quicksum(assign[i, j] for j in options) == 1)

for j in options:
    model.addCons(quicksum(weight[i] * assign[i, j] for i in items) <= capacity[j])
```

If an item may be unassigned, drop the equality constraint and add a penalty
term on `1 - sum_j assign[i, j]`.

## Absolute deviation penalty

Linearise `|actual[i] - target[i]|` via a non-negative slack variable.

```python
dev = {i: model.addVar(lb=0, name=f"dev_{i}") for i in I}

for i in I:
    model.addCons(actual[i] - target[i] <= dev[i])
    model.addCons(target[i] - actual[i] <= dev[i])

penalty_cost = penalty_weight * quicksum(dev[i] for i in I)
```

The minimisation objective forces `dev[i]` to the exact absolute value at
optimality. **Never** call Python's built-in `abs()` on a SCIP expression — it
returns a Python object that SCIP will refuse to add as a constraint.

## Route arcs

Model multi-vehicle routing as a flow on a directed graph with depot
source/sink nodes.

```python
START = "depot_start"
END = "depot_end"
nodes_from = [START, *locations]
nodes_to = [*locations, END]
arcs = [
    (i, j)
    for i in nodes_from
    for j in nodes_to
    if i != j and not (i == START and j == END)
]

x = {
    (k, i, j): model.addVar(vtype="B", name=f"x_{k}_{i}_{j}")
    for k in vehicles
    for i, j in arcs
}

for k in vehicles:
    model.addCons(quicksum(x[k, START, j] for j in locations) == 1)
    model.addCons(quicksum(x[k, i, END] for i in locations) == 1)

    for i in locations:
        incoming = quicksum(x[k, j, i] for j in nodes_from if (j, i) in arcs)
        outgoing = quicksum(x[k, i, j] for j in nodes_to if (i, j) in arcs)
        model.addCons(incoming == outgoing)
        model.addCons(outgoing <= 1)
```

Degree and continuity constraints alone permit disconnected sub-cycles. **Add
subtour elimination** (next section) whenever you model routing.

## MTZ subtour elimination

Polynomial-size subtour elimination via ordering variables.

```python
order = {
    (k, i): model.addVar(lb=1, ub=max(1, len(locations)), name=f"order_{k}_{i}")
    for k in vehicles
    for i in locations
}

n = len(locations)
for k in vehicles:
    for i in locations:
        for j in locations:
            if i != j:
                model.addCons(
                    order[k, i] - order[k, j] + n * x[k, i, j] <= n - 1
                )
```

MTZ is weaker than exponential SECs but adds only `O(n^2)` constraints per
vehicle, which is the right trade-off for small/medium routing instances and
benchmark-grade time limits.
