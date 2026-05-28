---
name: earthquake-plate-boundary-distance
description: Find the earthquake furthest from a tectonic plate's boundary, restricted to earthquakes inside that plate, using GeoPandas with a Pacific-centered projected CRS. Default target is the Pacific plate against PB2002 data. Use when the user asks for the deepest-interior or farthest-from-boundary earthquake within a plate, when the task supplies PB2002 plates/boundaries JSON plus an earthquakes GeoJSON, or whenever a point-to-line distance must cross the antimeridian without splitting the polygon.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python with geopandas, shapely, pyproj. Reads local JSON files; no network.
---

```yaml
purpose: >
  Identify the earthquake that lies the greatest planar distance from a tectonic
  plate's boundary, considering only earthquakes inside that plate. Default
  target is the Pacific plate against PB2002. The output is a single JSON
  record with id, place, ISO-8601 UTC time, magnitude, latitude, longitude,
  and distance_km (rounded to 2 decimal places). The procedure handles the
  Pacific plate's antimeridian crossing by reprojecting to a Pacific-centered
  CRS before any spatial operation.

trigger_when:
  - User asks for the earthquake furthest from a plate boundary, inside that plate
  - Task supplies PB2002 plates and boundaries JSON plus an earthquakes GeoJSON
  - Output is required at /root/answer.json with id, place, time, magnitude, lat, lon, distance_km
  - Point-to-line distance must be computed across the antimeridian without splitting the polygon
  - User explicitly requests "GeoPandas projections" for a plate-tectonics + earthquake question

do_not_use_when:
  - Question only needs nearest earthquake to ANY boundary, not interior-most
  - Question is about volcanic vents, eruptions, or seismic moment tensors rather than epicenters
  - No projected-distance requirement and angular (degree) distance is acceptable
  - Plate of interest is not represented in PB2002 (e.g., microplates absent from the dataset)

scope_and_approval: >
  Read-only on /root/earthquakes_2024.json, /root/PB2002_plates.json, and
  /root/PB2002_boundaries.json. Writes only the output JSON (default
  /root/answer.json). No network calls. No approval needed for the default
  paths — confirm with the user before redirecting to a different output.

steps:
  - name: confirm-inputs
    description: >
      Verify the three input files exist at /root/. Peek at the first feature
      of each (one line each) to confirm GeoJSON shape, attribute column
      names on the plates file (PlateName/Code/etc.), and that earthquakes
      carry properties.time (ms epoch), properties.mag, properties.place,
      and a Feature-level id. See references/data-formats.md.
  - name: load-datasets
    description: >
      Load each JSON as a GeoDataFrame in EPSG:4326. Parse the raw JSON
      manually (do not rely on gpd.read_file) so the Feature-level id on
      earthquake records is preserved as a column.
  - name: identify-plate
    description: >
      Locate the target plate row. Search columns in order — name columns
      (PlateName, Name, plate_name) by case-insensitive substring, then
      code columns (Code, PB2002) by exact upper-case match. Default
      target is "Pacific" / "PA".
  - name: choose-projected-crs
    description: >
      Pick a Pacific-centered projected CRS so the plate is contiguous and
      distances come out in metres. Default — Lambert Azimuthal Equal Area
      centered at (0°, 160°W). See references/projections.md for
      alternatives and what to avoid.
  - name: reproject-then-spatial-ops
    description: >
      Call to_crs on plates and earthquakes BEFORE any within/distance
      operation. Reprojecting first is what resolves the antimeridian
      crossing regardless of how the source GeoJSON stored the polygon.
  - name: filter-to-plate-interior
    description: >
      Keep only earthquakes whose projected Point is within the projected
      plate polygon. Use .within (strict interior); .intersects would
      include boundary-coincident points.
    depends_on: [reproject-then-spatial-ops]
  - name: measure-distance
    description: >
      For each surviving earthquake, compute geometry.distance against the
      projected plate polygon's .boundary. Result is in metres. The plate's
      own polygon boundary is geometrically identical to the union of
      PB2002 boundary segments that touch this plate, so using the polygon
      boundary is correct and simpler than filtering PB2002_boundaries.
    depends_on: [filter-to-plate-interior]
  - name: pick-winner
    description: >
      Take idxmax on the distance column. Pull the winning row's attributes
      from the unprojected (WGS84) earthquakes frame so latitude and
      longitude come out in degrees.
    depends_on: [measure-distance]
  - name: emit-answer
    description: >
      Write the seven required fields to /root/answer.json (or --out). Format
      rules — id is the Feature-level id (USGS "ids" is a comma-list, take
      first non-empty if that is all that is available); time converts ms
      epoch to "%Y-%m-%dT%H:%M:%SZ" in UTC; magnitude is a float; latitude
      and longitude are the EPSG:4326 point coordinates; distance_km is
      metres / 1000 rounded to 2 decimal places.
    depends_on: [pick-winner]

decisions:
  - signal: Pacific plate (or any antimeridian-crossing polygon) is involved.
    action: Use a Pacific-centered CRS (default LAEA at lon_0=-160). Never EPSG:3857, EPSG:4087, or any Greenwich-centered CRS.
  - signal: Plate is small and continental (e.g., Anatolian, Caribbean).
    action: A local UTM zone or a continent-appropriate equal-area CRS is fine; LAEA centered on the plate centroid is a safe default.
  - signal: gpd.read_file produces no `id` column on earthquakes.
    action: Reparse the JSON manually; copy each Feature's top-level `id` into properties.
  - signal: properties.time is an ISO string, not ms epoch.
    action: Parse with datetime.fromisoformat and reformat to "%Y-%m-%dT%H:%M:%SZ".
  - signal: Two or more plate rows match the requested name.
    action: Prefer the row with the largest area (Pacific is by far the largest "PA"-coded polygon if microplate PAs ever appear).
  - signal: No earthquakes fall inside the plate after filtering.
    action: Confirm the plate polygon projected correctly (visual inspection of bounds in the projected CRS) before assuming the dataset has no interior events.

scenarios:
  - need: Default Pacific-plate task with all inputs at the documented /root/ paths.
    action: Run scripts/solve.py with no arguments. Inspect printed JSON; confirm /root/answer.json exists.
    outcome: A single JSON record with the seven required fields, distance_km rounded to 2 decimal places.
  - need: Same task but for a different plate (e.g., Nazca).
    context: User asks "what about the Nazca plate?" — PB2002 has it under code NZ.
    action: Run scripts/solve.py --plate Nazca. The default LAEA CRS still works; consider --crs "+proj=laea +lat_0=-20 +lon_0=-90 +datum=WGS84 +units=m" for a Nazca-centered projection if results look skewed.
    outcome: Answer JSON for the Nazca plate's deepest-interior earthquake.
  - need: Plates file uses non-standard column names and the default name lookup misses.
    context: find_plate raises ValueError listing the columns present.
    action: Pass the matching value through --plate (e.g., the two-letter code) or extend PLATE_NAME_COLUMNS / PLATE_CODE_COLUMNS in solve.py.
    outcome: Plate row located; pipeline continues.

anti_patterns:
  - Calling .within or .distance in EPSG:4326 — the result is in degrees and meaningless across a basin.
  - Using EPSG:3857, EPSG:4087, or any Greenwich-centered CRS for the Pacific plate — splits the polygon at the antimeridian and silently produces wrong distances.
  - Treating Mercator distance as accurate — at ±60° latitude the scale factor is ~2, biasing the answer toward poleward earthquakes.
  - Relying on gpd.read_file to preserve the Feature-level id — it often does not; parse the JSON yourself.
  - Filtering with .intersects instead of .within when the question is "inside" the plate.
  - Reading properties.time as seconds — USGS earthquake feeds report milliseconds.
  - Rounding distance_km with format strings (e.g. f"{x:.2f}") instead of Python's round() — the task asks for the rounded number, not a string.
  - Using PB2002_boundaries.json's full LineString collection and forgetting to filter to segments adjacent to the target plate; using the plate polygon's own .boundary is equivalent and simpler.
```
