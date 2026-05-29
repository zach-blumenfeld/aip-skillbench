# Integration patterns

Canonical import-and-use pattern for the helpers in
`scripts/routing_data.py`. Treat this as a template — copy the parts that
fit the surrounding model code.

## Load and validate the task data

```python
import sys
sys.path.insert(0, "scripts")  # adapt to wherever the skill lives
from routing_data import (
    START, END,
    load_routing_data, build_node_distances, great_circle_miles,
    parse_report_route, route_to_report_ids,
    route_distance_internal, route_distance_reported_ids,
    check_route_structure, assert_close,
)

bundle = load_routing_data("/root/data.json")
depot              = bundle["depot"]               # {"latitude": ..., "longitude": ...}
station_locations  = bundle["station_locations"]   # list, in input order
station_ids        = bundle["station_ids"]         # list[int], input order
id_to_idx          = bundle["id_to_idx"]
idx_to_id          = bundle["idx_to_id"]
```

`load_routing_data` raises `ValueError` on duplicate IDs or
out-of-range coordinates — fail fast before building the model.

## Build the arc-set distance dict

```python
EARTH_RADIUS = 3960.0  # confirm from task statement
distances = build_node_distances(
    depot, station_locations,
    radius=EARTH_RADIUS,
    allow_direct_depot_to_depot=False,
)
```

Keys are `(from_node, to_node)` where each node is `START`, an `int`
station index in `0..n-1`, or `END`. Values are floats. **Use the same
dict in both optimization and validation** — never rebuild with a
different radius downstream.

## Optimization model — variable naming

Use internal indices inside the model:

```python
from_nodes = [START, *range(len(station_locations))]
to_nodes   = [*range(len(station_locations)), END]
# x[i, j, v] = 1 if vehicle v traverses arc (i, j); objective uses distances[i, j].
```

## Convert solver output to the report

```python
# Internal-index route returned by the solver:
route_nodes = [START, 3, 7, 2, END]

# Report form (station IDs at the intermediate positions):
report_route = route_to_report_ids(route_nodes, idx_to_id)
# -> [START, station_ids[3], station_ids[7], station_ids[2], END]
```

## Parse a report back into internal indices

```python
internal = parse_report_route(report_route, id_to_idx)
# -> [START, 3, 7, 2, END]
```

## Reconstruct and validate

```python
errors = check_route_structure(report_route, id_to_idx)
if errors:
    raise ValueError(f"route invalid: {errors}")

reconstructed = route_distance_reported_ids(report_route, distances, id_to_idx)
assert_close(reconstructed, model_reported_distance, tol=1e-6)
```

For multi-vehicle reports:

```python
total = sum(
    route_distance_reported_ids(v["route"], distances, id_to_idx)
    for v in report["vehicles"]
)
```

## CLI alternative

For a one-shot check from the shell:

```bash
python scripts/validate_route.py \
    --data /root/data.json \
    --report path/to/report.json \
    --earth-radius 3960.0 \
    --expected-distance 142.7
```

Exits 0 on success; 1 with a JSON diagnostic on failure.

## Quick data-file sanity check

```bash
python scripts/routing_data.py validate /root/data.json
```

Prints station count, depot coordinates, and ID range. Useful as a
first read on a new task.
