---
name: geospatial-analysis
description: Analyze geospatial data using geopandas with proper coordinate projections. Use when calculating distances between geographic features, performing spatial filtering, or working with plate boundaries and earthquake data.
license: MIT
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Analyze geospatial data with geopandas using proper coordinate
  projections. Project geographic data (EPSG:4326) to a metric CRS
  (EPSG:4087) before computing distances, combine multi-segment
  geometries with .unary_union, and use vectorized geopandas
  operations instead of hand-rolled formulas. Scope is the procedure
  for point/polygon/boundary workflows over earthquakes, tectonic
  plates, and similar geographic features.

trigger_when:
  - User asks to calculate distance between geographic features (points, lines, polygons).
  - Working with earthquake, plate, or boundary GeoJSON data.
  - Spatially filtering points by polygon containment.
  - Loading or working with .geojson / .json files that contain geometries.
  - User mentions plate boundaries, tectonic plates, or earthquake locations.
  - Need to find the nearest/furthest geographic feature from a set of candidates.

do_not_use_when:
  - Working with non-geographic tabular data that has no coordinates.
  - Task is purely cartographic rendering (drawing maps) with no spatial computation.
  - A specialized routing, geocoding, or raster-analysis skill is more appropriate than vector spatial ops.

steps:
  - name: load-data
    description: >
      Load geospatial inputs. Use gpd.read_file("file.json") for
      GeoJSON. For tabular coordinate data, build geometry with
      [Point(row["lon"], row["lat"]) for row in data] and wrap in
      gpd.GeoDataFrame(data, geometry=geometry, crs="EPSG:4326").
      Always set the CRS at construction time.
  - name: filter-attributes
    description: >
      Narrow the data before expensive spatial operations. Filter by
      attribute equality (e.g., gdf_plates[gdf_plates["Code"] ==
      "PA"]) or string pattern (e.g.,
      gdf_boundaries["Name"].str.contains("PA")). Reducing row count
      first makes projection and distance calls much cheaper.
  - name: spatial-filter
    description: >
      Apply spatial containment with .within(). Build the target
      polygon via target = subset.geometry.unary_union, then
      points_inside = gdf_points[gdf_points.within(target)]. Add
      .copy() on the resulting slice if you will mutate it
      downstream to avoid SettingWithCopyWarning.
  - name: combine-geometries
    description: >
      Merge multiple polygons or line segments into a single
      geometry with .geometry.unary_union before distance or
      containment operations. A single unioned geometry is both
      faster and more accurate than iterating segment-by-segment.
  - name: project-to-metric-crs
    description: >
      Convert geometries from EPSG:4326 (degrees) to a metric CRS
      such as EPSG:4087 with .to_crs("EPSG:4087") before any
      distance calculation. Project once outside loops, and project
      only the filtered subset — never the raw large dataset.
  - name: compute-distances
    description: >
      Call .distance() on projected geometries to get distances in
      meters, then divide by 1000.0 for kilometers. Assign as a
      column (gdf["distance_km"] = projected.geometry.distance(target)
      / 1000.0) so downstream sorting and reporting can use it.
  - name: rank-results
    description: >
      Use .nlargest(n, "distance_km") or .nsmallest(n,
      "distance_km") to retrieve furthest or nearest features.
      Extract a single row with .iloc[0] and report named fields
      (id, name, magnitude, distance_km) rather than positional
      indices.

decisions:
  - signal: Distances need to be computed between geographic features.
    action: Project both sides to EPSG:4087 (or another metric CRS) before calling .distance(). Never compute distance directly on EPSG:4326 geometries — the result is in degrees and is not a uniform unit on Earth's surface.
  - signal: Multiple boundary segments or polygons must be treated as one feature.
    action: Combine them with .geometry.unary_union before calling .distance() or .within().
  - signal: Dataset is large and only a subset is relevant.
    action: Filter by attribute first (equality, .str.contains), then project the small subset — not the other way around.
  - signal: Some features in the GeoDataFrame have no geometry.
    action: Filter with gdf[gdf.geometry.notna()] before spatial operations to avoid NaN/None propagation.
  - signal: Geometries cross the antimeridian (±180° longitude).
    action: Use geopandas spatial operations directly. Do not adjust longitudes by ±360 manually — geopandas handles wrap-around correctly.
  - signal: A filtered slice will be mutated (new column, in-place edit).
    action: Take .copy() on the slice before mutating to avoid SettingWithCopyWarning and silent aliasing bugs.

scenarios:
  - need: Find the earthquake within the Pacific plate that is furthest from any Pacific plate boundary.
    context: >
      Inputs are earthquake records with longitude/latitude fields
      plus plates.json and boundaries.json GeoJSON files. Plates
      carry "Code" and "PlateName"; boundaries carry "Name" with
      tokens like "PA" identifying adjacent plates.
    action: >
      (1) Build gdf_eq from the earthquake records as a
      GeoDataFrame in EPSG:4326. (2) Compute target_plate =
      gdf_plates[gdf_plates["Code"] == "PA"].geometry.unary_union
      and filter gdf_eq[gdf_eq.within(target_plate)].copy().
      (3) Project that subset to EPSG:4087. (4) Project and union
      the PA-related boundaries via
      gdf_boundaries[gdf_boundaries["Name"].str.contains("PA")]
      .to_crs("EPSG:4087").geometry.unary_union.
      (5) Assign earthquakes_in_plate["distance_km"] =
      eq_proj.geometry.distance(boundary_geom) / 1000.0.
      (6) Return earthquakes_in_plate.nlargest(1,
      "distance_km").iloc[0].
    outcome: The single furthest earthquake by metric distance, with the distance reported in kilometers.

anti_patterns:
  - Calling .distance() on EPSG:4326 geometries — returns degrees, not meters, and is incorrect outside a narrow band of latitudes.
  - Hand-implementing the Haversine formula instead of using geopandas projections plus .distance().
  - Iterating through individual boundary points to find the closest one — call .distance() once against the .unary_union of the boundary set.
  - Manually shifting longitudes by ±360 to handle the antimeridian — let geopandas spatial operations handle wrap-around.
  - Projecting a large GeoDataFrame to a metric CRS just to filter it down — filter on attributes first, then project the subset.
  - Projecting inside a loop instead of once before the loop.
  - Mutating a filtered slice without .copy() — produces SettingWithCopyWarning and silent corruption.
  - Implementing point-in-polygon checks by hand instead of using .within().
  - Forgetting to set crs="EPSG:4326" when constructing a GeoDataFrame from raw lon/lat — downstream .to_crs() will fail or produce wrong results.
```
