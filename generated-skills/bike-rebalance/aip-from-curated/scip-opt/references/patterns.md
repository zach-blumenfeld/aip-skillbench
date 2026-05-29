# PySCIPOpt Modeling Patterns

Load this file when the problem you are modeling matches one of the
patterns below. Each section gives the structural shape, the SCIP
expression, and the gotcha that bites if you skip it.

All snippets assume `from pyscipopt import Model, quicksum` and a `model`
already constructed.

## Binary Activation

Allow a continuous or integer quantity only when an option is "on". The
binary `use[i]` flips the upper bound of `q[i]` to 0 when off.

```python
use = {i: model.addVar(vtype="B", name=f"use_{i}") for i in I}
q = {i: model.addVar(lb=0, ub=upper[i], name=f"q_{i}") for i in I}

for i in I:
    model.addCons(q[i] <= upper[i] * use[i])
```

Use when: turning on a vehicle, opening a facility, activating an arc,
or any "pay a fixed cost only if used" pattern.

## Assignment

Each item is assigned to exactly one option; each option respects a
capacity over the items assigned to it.

```python
assign = {
    (i, j): model.addVar(vtype="B", name=f"assign_{i}_{j}")
    for i in items
    for j in options
}

for i in items:
    model.addCons(quicksum(assign[i, j] for j in options) == 1)

for j in options:
    model.addCons(
        quicksum(weight[i] * assign[i, j] for i in items) <= capacity[j]
    )
```

Use when: jobs to machines, customers to depots, bikes to stations
within a vehicle, packets to bins.

## Absolute Deviation Penalty

Penalize how far an actual value strays from a target. The two
inequalities together force `dev[i] >= |actual[i] - target[i]|`; the
minimization in the objective pulls `dev[i]` down to the tight side.

```python
dev = {i: model.addVar(lb=0, name=f"dev_{i}") for i in I}

for i in I:
    model.addCons(actual[i] - target[i] <= dev[i])
    model.addCons(target[i] - actual[i] <= dev[i])

penalty_cost = penalty_weight * quicksum(dev[i] for i in I)
```

**Never** write `abs(actual[i] - target[i])` against SCIP expressions —
Python's `abs()` does not produce a linear constraint and the model will
fail or silently misbehave. Always linearize with the two inequalities.

## Route Arcs (Vehicle Routing)

One binary per `(vehicle, arc)`. Each vehicle leaves the start depot
exactly once, enters the end depot exactly once, and at every interior
node flow in equals flow out.

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

Degree + continuity alone **permit disconnected cycles**. Pair this with
the MTZ subtour-elimination pattern below for any routing model.

## MTZ Subtour Elimination

Miller-Tucker-Zemlin ordering variables prevent disconnected cycles
inside a vehicle's tour: if arc `i -> j` is used, `j` must come strictly
after `i` in the visit order.

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
                model.addCons(order[k, i] - order[k, j] + n * x[k, i, j] <= n - 1)
```

MTZ is cheap and adequate for small / medium instances. For very large
routing problems consider lazy subtour cuts instead, but MTZ is the
correct default here.

## Combining Patterns

Most real problems compose these — e.g. a bike-rebalance model uses
*assignment* (bikes between stations), *binary activation* (a vehicle is
"used" when it carries any load), *absolute deviation* (penalty for
stations left away from their target inventory), and *route arcs +
MTZ* (each vehicle visits a sequence of stations once). Build the
constraint blocks pattern-by-pattern and label each block so the
debugger and validator can echo it back.
