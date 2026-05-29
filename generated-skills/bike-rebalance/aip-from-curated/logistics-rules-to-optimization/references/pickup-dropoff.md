# Inventory pickup/dropoff pattern

Use this pattern for rebalancing and material-movement problems where the
same node can be a source (pickup) or a sink (dropoff) depending on the
solver's decision, and the resource (vehicle) carries inventory between
nodes. Examples: bike-share rebalancing, scooter redistribution, warehouse
moves, swap-body container rebalancing.

## Signed service variable

Define a single signed service variable per (resource, location). One sign
convention beats a separate `pickup` / `dropoff` pair because it halves the
variable count and eliminates the "both at the same stop" branch.

**Convention (recommended)**

- `service[v, i] > 0`: pickup from location `i`, vehicle load **increases**,
  location inventory **decreases**.
- `service[v, i] < 0`: dropoff to location `i`, vehicle load **decreases**,
  location inventory **increases**.
- `service[v, i] == 0`: vehicle either does not visit `i`, or visits without
  exchanging units.

```python
service = {
    (v, i): model.addVar(vtype="I", lb=-vehicle_capacity, ub=vehicle_capacity, name=f"service_{v}_{i}")
    for v in vehicles
    for i in locations
}
```

## Gate service on the visit

If vehicle `v` does not visit location `i`, `service[v, i]` must collapse to
zero. Couple to the per-vehicle outgoing arcs:

```python
for v in vehicles:
    for i in locations:
        visit_i = quicksum(x[v, i, j] for j in to_nodes if j != i)
        model.addCons(service[v, i] <=  vehicle_capacity * visit_i)
        model.addCons(service[v, i] >= -vehicle_capacity * visit_i)
```

## Aggregate station inventory limits

The sum of service over all vehicles at a location is the **net change** in
that location's inventory. Bound it against the location's current stock
(for pickups) and its free space (for dropoffs):

```python
for i in locations:
    net_change = quicksum(service[v, i] for v in vehicles)
    free_space = storage_capacity[i] - initial_inventory[i]

    model.addCons(net_change <=  initial_inventory[i])   # pickup cannot exceed current stock
    model.addCons(net_change >= -free_space)             # dropoff cannot exceed free space
```

## Target as a soft objective (absolute deviation)

If the problem supplies a per-location desired net pickup/dropoff (e.g., a
forecaster's target), penalise the absolute deviation:

```python
unmet = {i: model.addVar(vtype="I", lb=0, name=f"unmet_{i}") for i in locations}

for i in locations:
    net_change = quicksum(service[v, i] for v in vehicles)
    model.addCons(net_change - target[i] <= unmet[i])
    model.addCons(target[i] - net_change <= unmet[i])
```

Then add `penalty_weight * quicksum(unmet[i] ...)` to the objective.

## Load propagation along selected arcs

Use the standard route-state propagation pattern (see
`constraint-snippets.md` → "Load or state transition along selected arcs"),
with `change_at_j = service[v, j]` when `j` is a location:

```python
M = 2 * vehicle_capacity

for v in vehicles:
    for i, j in arcs:
        change_at_j = service[v, j] if isinstance(j, int) else 0
        model.addCons(load[v, j] - load[v, i] - change_at_j <=  M * (1 - x[v, i, j]))
        model.addCons(load[v, j] - load[v, i] - change_at_j >= -M * (1 - x[v, i, j]))
```

## Extracting pickup / dropoff from the signed variable

After solving, split the signed value back into the reporting fields:

```python
service_value = model.getVal(service[v, i])
picked_up   = max(service_value, 0)
dropped_off = max(-service_value, 0)
```

By construction `picked_up * dropped_off == 0`, so the report never claims
both at the same stop.

## When NOT to use the signed-service form

- The task explicitly requires two separately-bounded decision variables
  (e.g., different unit costs for pickup vs dropoff).
- Pickups and dropoffs draw on *different* physical capacities at the same
  location (rare).
- The problem has mode binaries (`is_pickup[v, i]` / `is_dropoff[v, i]`)
  whose values are reported independently of the quantity.

In those cases, declare `pickup[v, i]` and `dropoff[v, i]` as separate
nonnegative integers and add a mutual-exclusion constraint
(`is_pickup[v, i] + is_dropoff[v, i] <= visit[v, i]`) plus linking to the
quantities.

## Connectivity warning

Vehicle load is **not** a connectivity flow in this model — it can increase
*or* decrease along the route — so the standard "single-commodity flow proves
the graph is connected" trick does not apply. Use a separate connectivity
mechanism (MTZ ordering vars, an artificial flow, DFJ cuts) to prevent
station-only cycles.
