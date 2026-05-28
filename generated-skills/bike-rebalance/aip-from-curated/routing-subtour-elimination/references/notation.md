# Base Notation for Routing MIPs

Load this when you are building a routing MIP from scratch and the
helper functions in `scripts/` will be wired to your model. Every
subtour-elimination function in this skill assumes the convention
below.

## Nodes and arcs

```python
START = "depot_start"      # source of every vehicle trip
END   = "depot_end"        # sink of every vehicle trip
vehicles = range(K)        # K vehicles
stations = range(n)        # n stations to visit

from_nodes = [START, *stations]
to_nodes   = [*stations, END]

# Self-loops excluded; the direct START -> END "skip" edge excluded.
arcs = [(i, j) for i in from_nodes for j in to_nodes
        if i != j and not (i == START and j == END)]
```

Two depot nodes (start / end) rather than one is a deliberate choice:
the asymmetry sharpens the flow / connectivity argument used by every
subtour-elimination family below.

## Decision variables

```python
x = {(v, i, j): model.addVar(vtype="B", name=f"x_{v}_{i}_{j}")
     for v in vehicles for (i, j) in arcs}
```

`x[v, i, j] == 1` iff vehicle `v` traverses arc `(i, j)`. Treat `x` as
the canonical decision variable family — extra families (loads, visit
flags, time slots) hang off this skeleton.

## Required base route constraints

Add these BEFORE any subtour-elimination family:

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

`scripts/route_setup.py::add_base_route_constraints` adds exactly the
block above; call it instead of retyping the constraints.

## Why this matters

Degree + continuity alone do NOT forbid a vehicle from having one
depot-to-depot path AND a separate closed cycle among stations.
Subtour-elimination constraints (MTZ, single-commodity flow, DFJ, or
lazy DFJ separation) plug into this skeleton to forbid the disconnected
cycle.

If you deviate from this notation (different depot naming, multi-period
indexing, multi-commodity loads), you can still use the methods in
`references/methods.md` by re-deriving each constraint family against
your variables. The helper scripts will not match.
