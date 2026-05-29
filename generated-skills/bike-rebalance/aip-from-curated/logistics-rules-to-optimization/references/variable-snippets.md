# Variable declaration snippets

Reusable PySCIPOpt variable families. Use these as scaffolds when introducing
new decision variables in a logistics optimization model. Names and index sets
are illustrative — substitute the problem's entity sets.

## Selection and assignment (binary)

Use binary variables when an option is selected.

```python
x = {(i, j): model.addVar(vtype="B", name=f"x_{i}_{j}") for i in I for j in J}
```

Common rules wired against this family:

```python
# each item i assigned to exactly one option j
for i in I:
    model.addCons(quicksum(x[i, j] for j in J) == 1)

# option j can handle at most capacity[j] items
for j in J:
    model.addCons(quicksum(x[i, j] for i in I) <= capacity[j])
```

## Route arcs (binary, per resource)

Use binary arc variables when the order of visits matters.

```python
x = {
    (v, i, j): model.addVar(vtype="B", name=f"x_{v}_{i}_{j}")
    for v in vehicles
    for i, j in arcs
}
```

`x[v, i, j] = 1` means vehicle/resource `v` goes directly from node `i` to
node `j`.

## Visit indicator

Define `visit` from route arcs instead of creating a second binary, unless the
model needs it repeatedly. Keeping it as an expression saves a variable plus
the linking constraint.

```python
visit = quicksum(x[v, i, j] for j in to_nodes if j != i)
```

If a standalone variable is useful (e.g., it appears in many constraints):

```python
visit = {(v, i): model.addVar(vtype="B", name=f"visit_{v}_{i}") for v in vehicles for i in locations}

for v in vehicles:
    for i in locations:
        model.addCons(visit[v, i] == quicksum(x[v, i, j] for j in to_nodes if j != i))
```

## Quantity, load, inventory, and time (integer / continuous)

```python
load = {
    (v, i): model.addVar(vtype="I", lb=0, ub=vehicle_capacity, name=f"load_{v}_{i}")
    for v in vehicles for i in nodes
}

service = {
    (v, i): model.addVar(vtype="I", lb=-vehicle_capacity, ub=vehicle_capacity, name=f"service_{v}_{i}")
    for v in vehicles for i in locations
}

inventory = {
    (i, t): model.addVar(vtype="I", lb=0, ub=storage_capacity[i], name=f"inventory_{i}_{t}")
    for i in locations for t in periods
}

arrival = {
    (v, i): model.addVar(vtype="C", lb=0, name=f"arrival_{v}_{i}")
    for v in vehicles for i in nodes
}
```

Use integer variables for physical unit counts when the output must be
integer-valued (bikes, pallets, units). Use continuous for time, distance,
fractional flow, utilization. Always set tight `lb`/`ub` from real bounds —
this both tightens the relaxation and gives a non-arbitrary big-M for any
linking constraint.

## Variable-type cheat sheet

- **Binary (`vtype="B"`)** — yes/no choices: selected, opened, visited, mode,
  arc used.
- **Integer (`vtype="I"`)** — counts and physical units: load, inventory,
  units moved, slack on a discrete target.
- **Continuous (`vtype="C"`)** — time, flow, cost, utilization, fractional
  quantities, MTZ ordering helpers.
