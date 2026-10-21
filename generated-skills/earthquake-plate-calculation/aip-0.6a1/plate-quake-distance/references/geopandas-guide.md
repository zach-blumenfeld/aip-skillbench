# GeoPandas distance and filtering guide (plate / earthquake analysis)

Load only when you must deviate from `scripts/analyze.py` (different file format, debugging an unexpected result) or explain the method.

## Coordinate systems

| Coordinate System | Type | Units | Use Case |
|---|---|---|---|
| EPSG:4326 (WGS84) | Geographic | Degrees (lat/lon) | Data storage, display, `.within()` filtering |
| EPSG:4087 (World Equidistant Cylindrical) | Projected | Meters | Distance calculations |

Critical rule: never calculate distances in EPSG:4326 — `.distance()` there returns degrees, not metres. Project once (`to_crs("EPSG:4087")`), then `distance_m / 1000.0` = km.

## Pattern

```python
import geopandas as gpd
from shapely.geometry import Point

gdf_plates = gpd.read_file(plates_path)          # GeoJSON loads directly
gdf_bounds = gpd.read_file(boundaries_path)
geometry = [Point(eq["longitude"], eq["latitude"]) for eq in quakes]
gdf_eq = gpd.GeoDataFrame(quakes, geometry=geometry, crs="EPSG:4326")

plate = gdf_plates[gdf_plates["Code"] == "PA"].geometry.union_all()   # or PlateName == "Pacific"
inside = gdf_eq[gdf_eq.within(plate)].copy()                           # copy before adding columns

M = "EPSG:4087"
pa_bounds = gdf_bounds[(gdf_bounds["PlateA"] == "PA") | (gdf_bounds["PlateB"] == "PA")]
boundary = pa_bounds.to_crs(M).geometry.union_all()                    # one geometry, one distance call
inside["distance_km"] = inside.to_crs(M).geometry.distance(boundary) / 1000.0
furthest = inside.nlargest(1, "distance_km").iloc[0]
```

`.unary_union` (named in older guides) is the deprecated spelling of `.union_all()`; both work in geopandas 1.0.1. `gdf_bounds["Name"].str.contains("PA")` selects the same PA segments as the PlateA/PlateB test.

## Performance

1. Filter before projecting (project only the in-plate subset).
2. Project once, not in loops.
3. Union the boundary segments, then make a single `.distance()` call.
4. `.copy()` filtered frames before adding columns.

## Pitfalls

| Issue | Problem | Solution |
|---|---|---|
| Distance in degrees | Using EPSG:4326 for distances | Project to EPSG:4087 |
| Antimeridian | Manual ±360 longitude shifts; or using the plate polygon outline, which has artificial edges at ±180° | Use geopandas operations and the boundaries file |
| Slow | Distance to each boundary vertex separately | `.union_all()` + one `.distance()` |
| Missing geometries | Features without geometry | `gdf[gdf.geometry.notna()]` |
| PROJ version drift | EPSG:4087 northings are spherical in PROJ 9.4 (pyproj 3.7.0 wheels) but ellipsoidal in PROJ 9.8, so the same event's distance differs by up to ~0.3% | Compute in the task's own environment; do not mix results across environments |
| 3-D points | USGS GeoJSON points carry depth; `read_file` tags them EPSG:4979 | Build 2-D points from lon/lat in EPSG:4326 |

Do not implement Haversine formulas, manual point-in-polygon tests, or loops over boundary points: slower, more error-prone, and they diverge from the projected-distance result the task expects.
