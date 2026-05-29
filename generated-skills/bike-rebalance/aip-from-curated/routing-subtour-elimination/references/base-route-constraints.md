# Required Base Route Constraints

Every subtour-elimination method below assumes the routing model already enforces flow degree and a single depot-to-depot path per vehicle. Add these before any subtour method, regardless of which method you pick.

## Base notation

```python
START = "depot_start"
END = "depot_end"
vehicles = range(K)
stations = range(n)
from_nodes = [START, *stations]
to_nodes = [*stations, END]
arcs = [(i, j) for i in from_nodes for j in to_nodes if i != j and not (i == START and j == END)]

x = {(v, i, j): model.addVar(vtype="B", name=f"x_{v}_{i}_{j}") for v in vehicles for i, j in arcs}
```

## Base constraints

```python
for v in vehicles:
    model.addCons(quicksum(x[v, START, j] for j in stations) == 1)
    model.addCons(quicksum(x[v, i, END] for i in stations) == 1)

    for i in stations:
        incoming = quicksum(x[v, j, i] for j in from_nodes if j != i)
        outgoing = quicksum(x[v, i, j] for j in to_nodes if j != i)
        model.addCons(incoming == outgoing)
        model.addCons(outgoing <= 1)
```

These constraints alone permit station-only cycles that are disconnected from `START`. Subtour elimination prevents that.
