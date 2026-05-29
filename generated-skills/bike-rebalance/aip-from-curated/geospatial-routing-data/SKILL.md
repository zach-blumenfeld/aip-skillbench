---
name: geospatial-routing-data
description: Geospatial routing data handling for depot and station coordinates, route node IDs, internal index mappings, great-circle distance matrices, and route-distance reconstruction. Use when optimization or reporting tasks involve latitude/longitude, station IDs, depots, distance metrics, vehicle routes, or validating travel distance from reported paths.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Handle geospatial routing data for vehicle routing and rebalancing
  tasks: depot and station coordinates, station IDs vs internal indices,
  great-circle distance matrices over the depot-stations arc set, and
  reconstruction of travel distance from a reported station sequence.
  Insulates the agent from the two main hazards — mixing user-facing
  station IDs with internal array indices, and using a distance metric
  (formula, Earth radius, or unit) different from the one the task
  declares.

trigger_when:
  - Building a routing or rebalancing optimization model that needs a distance matrix between a depot and stations.
  - Validating a routing report by recomputing reported travel distance from coordinates.
  - The task data file (e.g., /root/data.json) contains latitude/longitude pairs and a station id list.
  - Converting solver outputs (internal indices) to user-facing station IDs for reporting.
  - Parsing a reported route (depot_start ... station_id ... depot_end) back into internal indices for downstream checks.

do_not_use_when:
  - Routing distances are supplied as a precomputed matrix and the task explicitly forbids recomputing them from coordinates.
  - The task uses a non-great-circle distance metric and supplies its own distance function — use that function and skip the arc-set construction here.

steps:
  - name: load-and-validate-data
    description: >
      Parse the task data JSON, validate latitude/longitude ranges,
      deduplicate station IDs, and build id-to-index and index-to-id
      mappings. Delegates to load_routing_data in
      scripts/routing_data.py. CLI sanity check:
      `python scripts/routing_data.py validate <path>`.
    script: scripts/routing_data.py
    inputs:
      - name: data-path
        type: string
        description: Filesystem path to the task data JSON (typically /root/data.json).
    outputs:
      - name: depot
        type: object
        description: Validated {latitude, longitude}.
      - name: station-locations
        type: list[object]
        description: Validated {latitude, longitude}, in input order.
      - name: station-ids
        type: list[integer]
        description: Station IDs, in input order. Arbitrary integers — do not assume 0..n-1.
      - name: id-to-idx
        type: object
      - name: idx-to-id
        type: object
  - name: select-distance-metric
    description: >
      Read the task statement to identify the declared distance formula,
      Earth radius, and unit. See references/distance-metric-choice.md.
      The library defaults to great-circle miles with Earth radius
      3960.0 — confirm before relying on the default; never silently
      substitute a different formula, radius, or unit.
    outputs:
      - name: metric-spec
        type: object
        description: "Object with formula name, earth_radius, and output unit."
  - name: build-distance-matrix
    description: >
      Compute distances between depot_start, every station, and
      depot_end using the selected metric. Delegates to
      build_node_distances in scripts/routing_data.py. Use the resulting
      dict in both the optimization model and downstream validation —
      do not rebuild with a different radius later.
    script: scripts/routing_data.py
    inputs:
      - name: depot
        type: object
      - name: station-locations
        type: list[object]
      - name: metric-spec
        type: object
    outputs:
      - name: distances
        type: object
        description: "Dict keyed by (from_node, to_node) — node is depot_start, depot_end, or an int station index — values are float miles (or the unit chosen in metric-spec)."
  - name: convert-routes-between-ids-and-indices
    description: >
      Use internal indices inside the optimization model and original
      station IDs in the final report. Convert via route_to_report_ids
      (model -> report) and parse_report_route (report -> internal) in
      scripts/routing_data.py. Never assume station IDs are 0..n-1.
      See references/usage-examples.md for the full integration pattern.
    script: scripts/routing_data.py
    inputs:
      - name: route-nodes-internal
        type: list[object]
        description: Route as it comes from the solver — depot_start, int indices, depot_end.
      - name: id-to-idx
        type: object
      - name: idx-to-id
        type: object
    outputs:
      - name: report-route
        type: list[object]
        description: Route in reported form, with depot_start/depot_end labels and station IDs in between.
  - name: validate-route-and-recompute-distance
    description: >
      Run route structural checks (depot endpoints, valid station IDs,
      no repeats unless allowed, non-empty stations) and recompute
      travel distance from coordinates using the same distance matrix.
      Compare against the model-reported distance with relative +
      absolute tolerance. CLI:
        python scripts/validate_route.py --data <path> --report <path>
            --earth-radius <R> [--expected-distance <D>]
      Importable equivalents (route_distance_reported_ids,
      check_route_structure, assert_close) live in
      scripts/routing_data.py for inline use.
    script: scripts/validate_route.py
    inputs:
      - name: distances
        type: object
      - name: report
        type: object
        description: "Routing report: {vehicles: [{route: [...]}], travel_distance?: float}."
      - name: id-to-idx
        type: object
    outputs:
      - name: travel-distance
        type: float
        description: Sum of recomputed per-vehicle distances.
      - name: checks-passed
        type: boolean

anti_patterns:
  - Mixing user-facing station IDs with internal array indices in the same data structure. Choose one and convert explicitly at the boundary using route_to_report_ids and parse_report_route.
  - Assuming station IDs are 0..n-1. IDs are arbitrary integers — always go through id_to_idx and idx_to_id.
  - Using Euclidean distance on raw latitude/longitude degrees. Degrees are not a planar metric; error grows with latitude.
  - Using a different Earth radius from what the task declares (e.g., 6371 km vs 3960 mi vs 3958.8 mi). The geometry is identical but the objective scales silently.
  - Mixing miles, kilometers, and meters between the model objective and the report.
  - Rounding distances inside the optimization objective. Keep the matrix in floats; round only for display.
  - Forgetting to clamp the cosine in great-circle distance to [-1, 1]. Floating-point drift can push math.acos out of domain on near-identical points; routing_data.great_circle_miles already clamps.
  - Copying the model-reported travel distance straight into the final report. Always recompute from coordinates and compare with tolerance.
  - Omitting depot_start / depot_end labels when building the arc set, which lets the solver report an open path instead of a closed depot tour.
  - Allowing a direct (depot_start, depot_end) arc when the model requires at least one station per vehicle. Pass allow_direct_depot_to_depot=False (the default).
```
