---
name: geospatial-analysis
description: "Analyze geospatial data with geopandas while enforcing the projection discipline that makes distance calculations correct (EPSG:4326 for storage, EPSG:4087 for distance). Use when calculating distances between geographic features, performing spatial filtering, finding furthest/closest points to a boundary, or working with plate boundaries, earthquakes, and other lat/lon datasets."
license: MIT
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3 with geopandas, shapely, and pandas. Helpers in scripts/geo_ops.py.
---

```yaml
purpose: >
  Analyze geographic data (points, lines, polygons) with geopandas while
  enforcing the projection discipline that makes distance calculations
  correct. The flow is: load source data into a GeoDataFrame in EPSG:4326,
  filter points to a polygon via `.within()` against `.unary_union`,
  project to EPSG:4087 (World Equidistant Cylindrical) for any distance
  work, return distances in kilometres, and select extremes. The bundled
  `scripts/geo_ops.py` helper keeps the "never compute distance in
  EPSG:4326" rule and the metre→kilometre conversion in one place.
  Authored for the earthquake-vs-plate-boundary pattern but applies to any
  point/polygon/line analysis on Earth.

trigger_when:
  - Calculating the distance between geographic features (point→line, point→polygon, point→point).
  - Filtering points by polygon membership (e.g. earthquakes inside a specific tectonic plate).
  - Working with plate boundaries, earthquake catalogs, or any lat/lon point dataset.
  - Loading GeoJSON files or converting raw lat/lon records into a GeoDataFrame.
  - Finding the furthest or closest point to a boundary or set of features.
  - User mentions geopandas, shapely, CRS/EPSG, projections, spatial join, `.within`, or `.distance`.

do_not_use_when:
  - The data has no geographic coordinates — this skill is for lat/lon analysis, not generic 2-D geometry.
  - The task requires great-circle distances at antipodal or continent-spanning scale where EPSG:4087's tangential distortion matters; pick a region-appropriate metric CRS (e.g. a local UTM zone) instead.

scope_and_approval: >
  Read-only on input files. All computation is in-memory GeoDataFrames;
  the helper writes no files, makes no network calls, and performs no
  destructive operations. Safe to run without prompting.

steps:
  - name: load-geospatial-data
    description: >
      Load source data into a GeoDataFrame in EPSG:4326 (the canonical
      storage CRS). For GeoJSON / shapefile / any geopandas-readable file,
      use `load_geojson(path)`. For raw records with latitude/longitude
      fields (e.g. an earthquake catalog), use
      `points_from_records(records, lat_key, lon_key)`. Non-coordinate
      columns are preserved as attributes.
    script: scripts/geo_ops.py
    inputs:
      - name: input-source
        type: object
        description: Path to a geospatial file OR list of dict records carrying lat/lon fields.
    outputs:
      - name: gdf
        type: object
        description: GeoDataFrame in EPSG:4326 with attribute columns intact.
  - name: spatial-filter
    description: >
      Reduce a point GeoDataFrame to those falling inside a polygon (or
      the union of several polygons). Call
      `filter_points_within(gdf_points, gdf_polygon, where=...)` and pass
      an attribute-based mask over the polygon GeoDataFrame — e.g.
      `gdf_plates["Code"] == "PA"`, `gdf_plates["PlateName"] == "Pacific"`,
      or a substring `gdf_plates["Name"].str.contains("PA")`. The helper
      `.unary_union`s the matching features before testing membership and
      returns an independent copy (so adding columns later does not raise
      pandas' SettingWithCopyWarning). Skip this step when the analysis
      covers all input points.
    script: scripts/geo_ops.py
    depends_on: [load-geospatial-data]
    inputs:
      - name: gdf-points
        type: object
      - name: gdf-polygon
        type: object
      - name: where
        type: object
        nullable: true
        description: Optional pandas boolean mask over `gdf-polygon` to restrict membership before the union.
    outputs:
      - name: points-inside
        type: object
        description: Copy of `gdf-points` containing only rows whose geometry is within the (unioned) polygon.
  - name: compute-distance-to-target
    description: >
      Compute each point's shortest distance to the target feature(s) with
      `distance_km_to(gdf_points, gdf_target, where=...)`. The helper
      projects both inputs to EPSG:4087, drops missing geometries,
      `.unary_union`s the target so the distance is to the combined
      geometry (not per-segment), calls `.distance()`, and adds
      `distance_m` and `distance_km` columns to a *copy* of the input
      points (still in EPSG:4326). Use `where` to scope the target —
      `(gdf_boundaries["PlateA"] == "PA") | (gdf_boundaries["PlateB"] == "PA")`
      when boundary features encode adjacent plates explicitly,
      `gdf_boundaries["Name"].str.contains("PA")` when only a name string
      is available. NEVER call `.distance()` directly on EPSG:4326
      geometries — the value is degrees, not metres, and shrinks toward
      the poles.
    script: scripts/geo_ops.py
    depends_on: [load-geospatial-data]
    inputs:
      - name: gdf-points
        type: object
      - name: gdf-target
        type: object
        description: GeoDataFrame of points, lines, or polygons to measure distance against.
      - name: where
        type: object
        nullable: true
        description: Optional pandas boolean mask over `gdf-target`.
    outputs:
      - name: gdf-points-with-distance
        type: object
        description: A new GeoDataFrame — same rows as `gdf-points` plus `distance_m` and `distance_km` columns.
  - name: select-extreme-point
    description: >
      Pick the furthest or closest point with
      `extreme_by_distance(gdf, mode, n, column='distance_km')`, a thin
      wrapper over `nlargest` / `nsmallest`. `mode='max'` → furthest;
      `mode='min'` → closest. Always returns a GeoDataFrame slice; use
      `.iloc[0]` if the consumer wants a single row as a Series.
    script: scripts/geo_ops.py
    depends_on: [compute-distance-to-target]
    inputs:
      - name: gdf-points-with-distance
        type: object
      - name: mode
        type: string
        description: '"max" for furthest, "min" for closest.'
      - name: 'n'
        type: integer
        description: Number of rows to return.
    outputs:
      - name: extreme-rows
        type: object
        description: Top-n rows ordered by `distance_km` in the requested direction.

scenarios:
  - need: Find the earthquake inside the Pacific plate that is furthest from any Pacific-related plate boundary.
    action: >
      Load earthquakes via `points_from_records` and plates / boundaries
      via `load_geojson`. Call
      `filter_points_within(gdf_eq, gdf_plates, where=gdf_plates["Code"] == "PA")`
      to keep only earthquakes inside the Pacific plate, then
      `distance_km_to(filtered, gdf_boundaries, where=gdf_boundaries["Name"].str.contains("PA"))`,
      then `extreme_by_distance(..., mode='max', n=1).iloc[0]`.
    outcome: A single row carrying the furthest earthquake's attributes plus its `distance_km` to the nearest Pacific-related boundary.
  - need: Boundary features for a plate are split across many segments.
    action: >
      Let the helpers handle the union — both `filter_points_within` and
      `distance_km_to` `.unary_union` the target features after applying
      `where`, so segments behave as a single geometry and `.distance()`
      returns the shortest distance to any segment in one call.
    outcome: One distance value per point, to the combined boundary — no per-segment loop, no manual min.
  - need: Boundary GeoJSON encodes the two adjacent plates as separate columns (`PlateA`, `PlateB`) rather than a substring.
    action: Pass `where=(gdf_boundaries["PlateA"] == "PA") | (gdf_boundaries["PlateB"] == "PA")` to `distance_km_to`.
    outcome: Only boundaries that actually involve plate PA are unioned and measured against.
  - need: Working dataset is large (millions of points) and only a small region is in scope.
    action: >
      Filter in EPSG:4326 first (`filter_points_within` or a plain
      attribute mask), then call `distance_km_to` on the reduced subset.
      The helper projects to EPSG:4087 internally; projecting before
      filtering reprojects rows you will throw away.
    outcome: Same result, far less projection work.

anti_patterns:
  - Calling `.distance()` on EPSG:4326 geometries. The result is in *degrees*, not metres, and a degree of longitude at the equator is ~111 km while a degree near the pole is far less — every distance is silently wrong.
  - Implementing your own Haversine formula. The point of the skill (and geopandas) is correct projected distances; `distance_km_to` already enforces the projection.
  - Iterating per boundary segment and taking the minimum. Use `.unary_union` (already handled inside the helpers) so a single `.distance()` call returns the shortest distance to the combined geometry.
  - Projecting a large GeoDataFrame to EPSG:4087 first and then filtering on attributes. Filter (or `.within`) in EPSG:4326, then project the small subset.
  - Manually adjusting longitudes by ±360° to handle the antimeridian. Geopandas' projected geometries handle the wrap.
  - Looking for the new columns in the original GeoDataFrame after calling `distance_km_to`. It returns a *new* GeoDataFrame; reassign the result.
  - Forgetting that `nlargest(1, ...)` returns a one-row DataFrame, not a Series. Use `.iloc[0]` if the consumer wants the row as a Series.
  - Leaving rows whose geometry is missing in the input. `distance_km_to` drops them from the *target* but not from the points — filter beforehand with `gdf[gdf.geometry.notna()]` if the points dataset can contain nulls.
```
