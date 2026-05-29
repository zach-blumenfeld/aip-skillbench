---
name: geospatial-routing-data
description: Geospatial routing data handling for depot and station coordinates, route node IDs, internal index mappings, great-circle distance matrices, and route-distance reconstruction. Use when optimization or reporting tasks involve latitude/longitude, station IDs, depots, distance metrics, vehicle routes, or validating travel distance from reported paths.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Pure-Python (3.8+) standard library — `json`, `math`, `pathlib`. No third-party dependencies.
---

```yaml
purpose: >
  Safely turn a routing task's `data.json` (depot + stations) into the
  artifacts every downstream optimization step needs: validated
  coordinates, an internal-index / user-facing-ID round-trip, a
  great-circle arc-distance matrix matching the task's declared metric,
  reported↔internal route conversions, route-distance reconstruction
  with tolerance-based comparison, and structural route checks. The
  main risk this skill prevents is mixing user-facing station IDs with
  internal array indices, or using a different distance metric than the
  task declared. All conditional logic, numeric thresholds, and lookup
  tables are encoded in `scripts/` — the body is the execution graph.

trigger_when:
  - About to build a routing optimization model from a task `data.json` containing depot + station coordinates.
  - About to validate or score a `report.json` whose `travel_distance_miles` must reconcile against coordinates.
  - The agent needs a great-circle distance matrix between depot and stations.
  - The agent is choosing between Euclidean / haversine / spherical-cosines distance and needs to lock the task's declared metric.
  - A route uses string depot markers (e.g., `depot_start` / `depot_end`) interleaved with integer station IDs and the agent must walk it.
  - Reported and reconstructed travel distances disagree and the agent must find which conversion drifted.

do_not_use_when:
  - The task involves no geographic coordinates (pure abstract graph routing with a pre-supplied distance matrix).
  - The task uses a non-spherical distance (e.g., road-network shortest paths from an external routing service) — substitute that service for `build_arc_distances` instead of layering this skill on top.

scope_and_approval: >
  All operations are pure-Python reads of the task `data.json` and
  in-memory computation. No network calls, no filesystem writes outside
  what the caller chooses to do with the returned data. Safe to invoke
  without prompting.

steps:
  - name: load-stations-and-depot
    description: >
      Parse `data.json` once. Returns the depot, stations_data,
      station_ids, station_locations, and the two index dictionaries
      `id_to_idx` / `idx_to_id`. Validates latitude ∈ [-90, 90],
      longitude ∈ [-180, 180], and that station IDs are unique — fail
      fast on duplicates rather than overwriting silently in the dict
      comprehension. Use internal indices in optimization variables;
      use original station IDs in final reports. Convert at the
      boundary, never in the middle of the model.
    script: scripts/parse_data.py
    inputs:
      - name: data_path
        type: string
        description: Filesystem path to the task's `data.json` (typically `/root/data.json`).
    outputs:
      - name: depot
        type: object
        description: Validated {latitude, longitude} dict (degrees, floats).
      - name: stations_data
        type: list[object]
        description: Original station records — preserves every field on the input objects.
      - name: station_ids
        type: list[integer]
        description: User-facing station IDs in input order.
      - name: station_locations
        type: list[object]
        description: Per-station {latitude, longitude}, aligned by index with `station_ids`.
      - name: id_to_idx
        type: object
        description: dict[int station_id -> int internal index 0..n-1].
      - name: idx_to_id
        type: object
        description: dict[int internal index -> int station_id], the inverse.
      - name: n_stations
        type: integer

  - name: build-arc-distance-matrix
    description: >
      Build the canonical arc-distance dict over depot + stations.
      Uses `scripts/distance.py::build_arc_distances`, which builds
      `from_nodes = [DEPOT_START, 0..n-1]`, `to_nodes = [0..n-1,
      DEPOT_END]`, drops self-loops, and (by default) drops the direct
      `(DEPOT_START, DEPOT_END)` arc — matching the bike-rebalance rule
      that a vehicle must visit at least one station. Pass
      `allow_depot_to_depot=True` only when the task explicitly permits
      empty routes. Override `radius` only when the task declares a
      different Earth radius — bike-rebalance declares `3960.0`, which
      is the script default.
    script: scripts/distance.py
    depends_on: [load-stations-and-depot]
    inputs:
      - name: depot
        type: object
      - name: station_locations
        type: list[object]
      - name: radius
        type: float
        description: Earth radius matching the task's declared metric. Default 3960.0 (miles).
        nullable: true
      - name: allow_depot_to_depot
        type: boolean
        description: Include the direct DEPOT_START -> DEPOT_END arc. Default false. Set true only if the task allows empty routes.
        nullable: true
    outputs:
      - name: distances
        type: object
        description: dict[(from_node, to_node) -> float miles]. Keys mix the string depot labels and integer station indices.

  - name: convert-routes
    description: >
      Move routes across the indices↔IDs boundary. Use
      `internal_to_reported(route_nodes, idx_to_id)` when serializing
      an optimization solution for `report.json`. Use
      `parse_report_route(route, id_to_idx)` when consuming a
      `report.json` route for distance / load reconstruction — it
      raises on missing depot markers or unknown station IDs so a
      malformed report fails fast.
    script: scripts/routes.py
    depends_on: [load-stations-and-depot]
    inputs:
      - name: id_to_idx
        type: object
      - name: idx_to_id
        type: object
      - name: route_internal_or_reported
        type: list[object]
        description: Route in EITHER form — internal index list (to convert outward) or reported ID list (to convert inward).

  - name: reconstruct-route-distance
    description: >
      Recompute `travel_distance_miles` from coordinates rather than
      trusting the value reported in `report.json`. Per-vehicle
      `route_distance_reported(route, id_to_idx, distances)` parses
      the route and sums pairwise arcs. For the full report,
      `total_travel_distance_reported(report, id_to_idx, distances)`
      aggregates across vehicles. Compare against the reported value
      with `assert_close(actual, expected, tol=1e-6)` — relative
      tolerance scaled by `max(1, |expected|)`. Exact equality fails
      on the float rounding that report writers naturally introduce
      and is therefore the wrong check.
    script: scripts/routes.py
    depends_on: [build-arc-distance-matrix, convert-routes]
    inputs:
      - name: report
        type: object
        description: Parsed `report.json` (whole file or per-vehicle slice).
      - name: id_to_idx
        type: object
      - name: distances
        type: object
    outputs:
      - name: reconstructed_distance
        type: float
        description: Coordinate-derived total travel distance in the same units as `distances`.

  - name: validate-route-structure
    description: >
      Structural fail-fast on every vehicle's reported route BEFORE
      load / inventory checks run. `check_route_structure(route,
      id_to_idx)` enforces: first node is DEPOT_START, last node is
      DEPOT_END, every non-depot node is a known station ID, the route
      visits at least one station (vehicle cannot stay at depot), and
      no station is repeated within a single vehicle's route. Returns
      a list of problems — empty list = sound, non-empty list = fail
      this report. `check_stops_match_route(route, stops)` then
      confirms the non-depot sequence of `route` matches the
      `station_id` sequence of `stops` exactly — required because
      every downstream load / pickup / dropoff reconciliation is
      indexed by stop order.
    script: scripts/routes.py
    depends_on: [convert-routes]
    inputs:
      - name: route
        type: list[object]
      - name: stops
        type: list[object]
      - name: id_to_idx
        type: object
    outputs:
      - name: problems
        type: list[string]
        description: Empty list = route is structurally valid. Non-empty = each entry is one structural defect.

modes:
  - name: build-model
    body: >
      Building an optimization model from `data.json`. Walk steps in
      order: `load-stations-and-depot` -> `build-arc-distance-matrix`,
      then plug `distances` into the model's objective and use
      `idx_to_id` only when serializing routes back out at the end.
      No need to invoke `reconstruct-route-distance` /
      `validate-route-structure` during the solve loop — they are
      check tools, not model components.

  - name: validate-report
    body: >
      Validating an existing `report.json`. Run
      `load-stations-and-depot` and `build-arc-distance-matrix` first,
      then for every vehicle run `validate-route-structure` followed
      by `reconstruct-route-distance`. Fail the report on the first
      structural problem rather than trying to reconcile loads on a
      malformed route.

  - name: quick-distance-check
    body: >
      Just need to recompute one pair's miles to sanity-check a
      claim. Skip everything except `great_circle_miles` in
      `scripts/distance.py`. Confirm the task's Earth radius before
      calling — 3960.0 for bike-rebalance, but the value lives in
      `instruction.md` and overrides on other tasks happen.

scenarios:
  - need: Bike-rebalance solver setup — turn `data.json` into an arc-distance dict.
    context: Task declares great-circle miles, Earth radius 3960.0, vehicle must visit ≥1 station.
    action: Call `load_routing_data("/root/data.json")`, then `build_arc_distances(depot, station_locations)` with defaults. Use `distances[i, j]` as objective coefficients.
    outcome: Model objective coefficients match the task's declared metric; index/ID confusion is impossible because optimization variables only ever see internal indices.

  - need: Score a `report.json` whose travel distance feels too low.
    context: Reported `travel_distance_miles = 14.2` over 7 vehicles. Suspect the report writer summed Euclidean degrees, not miles.
    action: Run `load_routing_data` + `build_arc_distances`, then `total_travel_distance_reported(report, id_to_idx, distances)`. Compare against the report's number with `assert_close(actual, expected)`.
    outcome: Mismatch exposes the wrong metric immediately, with the coordinate-derived number as the authority.

  - need: Catch a vehicle that revisits the same station before load checks run.
    context: Vehicle 3's route is `[depot_start, 393, 871, 393, depot_end]`.
    action: "`check_route_structure(route, id_to_idx)` returns `[\"station 393 visited more than once\"]`."
    outcome: Report fails structural validation; downstream pickup/dropoff totals never need to be reconciled.

  - need: A station ID in a reported route does not exist in `data.json`.
    context: Route contains station ID 999 which is absent from `stations_data`.
    action: "`parse_report_route(route, id_to_idx)` raises `ValueError(\"unknown station id 999\")` — surfaces at the conversion boundary, not after partial summation."
    outcome: Fails fast at the boundary, with a specific bad ID rather than a generic KeyError later.

anti_patterns:
  - Using Euclidean distance on raw (latitude, longitude) degrees. Degrees of longitude are not constant length; the resulting "miles" are wrong everywhere except the equator. Use `great_circle_miles`.
  - Using haversine with a different Earth radius than the task declares. The bike-rebalance task pins 3960.0; other tasks may pin 6371.0 km. Read `instruction.md` before overriding the default.
  - Mixing miles and meters (or miles and kilometers) within the same model or report. Pick one in `build_arc_distances` and keep it everywhere.
  - Rounding distances inside the optimization objective. Rounded coefficients change the optimum. Round only at the reporting boundary.
  - Assuming station IDs are `0..n-1` and indexing arrays by raw ID. The task supplies arbitrary integer IDs — use `id_to_idx` / `idx_to_id`.
  - Comparing reconstructed and reported distances with `==`. Float rounding makes that check fail spuriously. Use `assert_close`.
  - Skipping `parse_report_route` and indexing `distances[a, b]` directly with raw report IDs. The arcs are keyed by internal indices and depot labels, so the lookup raises `KeyError` — fix the conversion, do not rewrite the distance map.
  - Converting lat/lon to radians at parse time. The validation step works on degrees; radian conversion lives inside `great_circle_miles` only. Doing both leads to double-conversion bugs.
  - Including a direct `(DEPOT_START, DEPOT_END)` arc when the task requires every vehicle to visit ≥1 station. The default in `build_arc_distances` already omits it — only flip `allow_depot_to_depot=True` after confirming the rule.
```
