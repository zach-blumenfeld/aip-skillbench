# geopandas cheatsheet — plate/earthquake distance workflow

Load `compute_distance.py` first — this file is only for understanding
*why* the script is written the way it is, or for porting the same logic
into another tool.

## The one rule that fails tasks silently

**Never compute `.distance()` on EPSG:4326 geometries.** Those are
degrees of latitude/longitude — one degree is ~111 km at the equator and
0 km at the poles. The number returned is unitless garbage. Always
re-project both operands to a metric CRS first:

```python
METRIC_CRS = "EPSG:4087"  # World Equidistant Cylindrical, meters
eq_proj = gdf_eq.to_crs(METRIC_CRS)
bounds_proj = gdf_boundaries.to_crs(METRIC_CRS)
distance_m = eq_proj.geometry.distance(bounds_proj.geometry.unary_union)
```

Divide meters by 1000 to get kilometers. The source skill notes
EPSG:4087 as the default; any true-metric projected CRS is fine as long
as both sides are in the same one.

## The one method that saves ~1000× work

Combine many boundary segments into a single geometry *before* calling
`.distance()`:

```python
boundary_geom = bounds_proj.geometry.union_all()   # one MultiLineString
dists = eq_proj.geometry.distance(boundary_geom)   # one call, Series out
```

Looping `for each boundary: for each quake: dist()` is O(N·M) and often
seconds-to-minutes slow. `union_all()` + a single `.distance()` call is
one vectorized sweep.

Note on API: on geopandas ≥ 1.0 use `.union_all()` (the method). The
`.unary_union` attribute still works but emits a DeprecationWarning that
pollutes script stderr and is slated for removal. Older curated
examples in this skill's `source/` show `.unary_union`; prefer
`.union_all()` in new code.

## Spatial filter: earthquakes inside a plate

```python
plate_geom = gdf_plates[gdf_plates["Code"] == plate_code].geometry.unary_union
eq_in_plate = gdf_eq[gdf_eq.within(plate_geom)].copy()
```

`.within()` is a vectorized boolean mask. The `.copy()` prevents later
column assignment from raising `SettingWithCopyWarning`.

## Picking the extremum

```python
furthest = eq_in_plate.nlargest(1, "distance_km").iloc[0]
nearest  = eq_in_plate.nsmallest(1, "distance_km").iloc[0]
```

## Pitfalls that bit prior runs

| Issue | Problem | Fix |
|-------|---------|-----|
| `distance()` in degrees | EPSG:4326 math | project to EPSG:4087 first |
| Antimeridian wraps | Manual ±360 adjustments | let geopandas handle it; it does |
| Slow distance | Loop per segment | `unary_union` + one `.distance()` |
| Missing geometry rows | USGS feed can carry nulls | `gdf[gdf.geometry.notna()]` |
| Boundary name substring match | `"PA"` matches `PAC-NA` | filter on `PlateA` / `PlateB` instead |
