# Constraint snippets

Runnable PySCIPOpt constraint blocks for the most common logistics rules.
Splice the block whose business rule matches; rename variables to match the
model.

## Capacity

```python
for r in resources:
    model.addCons(quicksum(amount[i, r] for i in items) <= capacity[r])
```

## Quantity allowed only when active (linking)

Use the tightest possible `M`. When `upper_bound[i]` is a real capacity or
horizon, use it; never invent an arbitrary large constant.

```python
for i in items:
    model.addCons(quantity[i] <= upper_bound[i] * use[i])
```

## Soft demand satisfaction (penalized unmet)

```python
unmet = {i: model.addVar(vtype="I", lb=0, name=f"unmet_{i}") for i in customers}

for i in customers:
    model.addCons(served[i] + unmet[i] >= demand[i])

penalty_cost = quicksum(penalty[i] * unmet[i] for i in customers)
```

## Absolute target deviation

Never apply Python's `abs()` to solver expressions. Linearise with a
nonnegative slack and two inequalities.

```python
dev = {i: model.addVar(vtype="C", lb=0, name=f"dev_{i}") for i in items}

for i in items:
    model.addCons(actual[i] - target[i] <= dev[i])
    model.addCons(target[i] - actual[i] <= dev[i])
```

`dev[i]` ends up equal to `abs(actual[i] - target[i])` at the optimum because
it appears in the (minimized) objective with a positive coefficient.

## Depot start and end

If every vehicle must be used:

```python
for v in vehicles:
    model.addCons(quicksum(x[v, START, j] for j in locations) == 1)
    model.addCons(quicksum(x[v, i, END] for i in locations) == 1)
```

If vehicles are optional, introduce a `use_vehicle` binary and tie it to
both endpoints:

```python
use_vehicle = {v: model.addVar(vtype="B", name=f"use_vehicle_{v}") for v in vehicles}

for v in vehicles:
    model.addCons(quicksum(x[v, START, j] for j in locations) == use_vehicle[v])
    model.addCons(quicksum(x[v, i, END] for i in locations) == use_vehicle[v])
```

## Route continuity and at-most-once visits per vehicle

```python
for v in vehicles:
    for i in locations:
        incoming = quicksum(x[v, j, i] for j in from_nodes if j != i)
        outgoing = quicksum(x[v, i, j] for j in to_nodes if j != i)

        model.addCons(incoming == outgoing)
        model.addCons(outgoing <= 1)
```

`outgoing <= 1` means vehicle `v` visits location `i` no more than once. It
does **not** prevent a different vehicle from also visiting `i` — for that,
add the global single-visit rule below.

## Global single-visit rule (split service NOT allowed)

Use only when the real rule forbids split service across vehicles/resources.

```python
for i in locations:
    model.addCons(
        quicksum(x[v, i, j] for v in vehicles for j in to_nodes if j != i) <= 1
    )
```

Do **not** add this rule when a single station's pickup/dropoff target may
need more than one vehicle (e.g., target exceeds one vehicle's capacity).

## Load or state transition along selected arcs (big-M coupling)

Use the same shape for any route-dependent state — load, arrival time,
battery charge, accumulated inventory. Pick `M` from real variable bounds
(`2 * vehicle_capacity` for load, `horizon` for time, etc.); never use a
generic huge constant.

If `state[j] = state[i] + change[j]` when arc `(i, j)` is used:

```python
M = 2 * vehicle_capacity

for v in vehicles:
    for i, j in arcs:
        change_at_j = service[v, j] if isinstance(j, int) else 0
        model.addCons(load[v, j] - load[v, i] - change_at_j <=  M * (1 - x[v, i, j]))
        model.addCons(load[v, j] - load[v, i] - change_at_j >= -M * (1 - x[v, i, j]))
```

## Time windows

```python
for v in vehicles:
    for i in locations:
        visit_i = quicksum(x[v, i, j] for j in to_nodes if j != i)
        model.addCons(arrival[v, i] >= earliest[i] - horizon * (1 - visit_i))
        model.addCons(arrival[v, i] <= latest[i]   + horizon * (1 - visit_i))

    for i, j in arcs:
        if j in locations:
            model.addCons(
                arrival[v, j] >= arrival[v, i]
                                + service_time.get(i, 0)
                                + travel_time[i, j]
                                - horizon * (1 - x[v, i, j])
            )
```

The `horizon * (1 - visit_i)` term relaxes the window when the vehicle does
not visit `i`; the same idea relaxes the propagation when the arc is not used.

## Conservation (inventory balance across periods)

```python
for i in locations:
    for t in range(len(periods) - 1):
        model.addCons(
            inventory[i, t + 1]
            == inventory[i, t]
            + quicksum(inbound[i, t, src] for src in sources)
            - quicksum(outbound[i, t, dst] for dst in destinations)
        )
```

Pair with `outbound[i, t, dst] <= inventory[i, t]` so the model cannot remove
stock that is not there.
