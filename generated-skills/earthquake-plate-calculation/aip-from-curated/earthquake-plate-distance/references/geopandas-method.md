# Manual geopandas method (fallback only)

Use only if `scripts/compute_distance.py` cannot run (e.g. you need a variant it does not
support). It reproduces the same method; keep every rule below.

```python
import geopandas as gpd, json
from shapely.geometry import Point

METRIC_CRS = "EPSG:4087"            # World Equidistant Cylindrical, metres
fc = json.load(open("/root/earthquakes_2024.json"))
rows = [{"id": f["id"], **f["properties"],
         "longitude": f["geometry"]["coordinates"][0],
         "latitude": f["geometry"]["coordinates"][1]} for f in fc["features"]]
gdf_eq = gpd.GeoDataFrame(rows, geometry=[Point(r["longitude"], r["latitude"]) for r in rows],
                          crs="EPSG:4326")      # Point(lon, lat) - lon first
plates = gpd.read_file("/root/PB2002_plates.json")
bounds = gpd.read_file("/root/PB2002_boundaries.json")

target = plates[plates["Code"] == "PA"].geometry.union_all()   # .unary_union on geopandas < 1.0
in_plate = gdf_eq[gdf_eq.within(target)].copy()                # filter before projecting

pb = bounds[(bounds["PlateA"] == "PA") | (bounds["PlateB"] == "PA")]
pb_geom = pb.to_crs(METRIC_CRS).geometry.union_all()           # combine once
in_plate["distance_km"] = in_plate.to_crs(METRIC_CRS).geometry.distance(pb_geom) / 1000.0
furthest = in_plate.nlargest(1, "distance_km").iloc[0]          # nsmallest for nearest
```

Rules
- Never take distances in EPSG:4326 (they come out in degrees). Project to EPSG:4087 first.
- Do not hand-roll Haversine, point-in-polygon, or loops over boundary vertices; use
  `.within()`, `.union_all()` + one `.distance()` call.
- Do not shift longitudes by +-360 for antimeridian-crossing plates; use the geometries as published.
- Drop features with no geometry: `gdf[gdf.geometry.notna()]`.
- Project once, not in a loop; `.copy()` filtered frames before adding columns.
- `bounds["Name"].str.contains("PA")` is the source's shortcut; matching PlateA/PlateB (or the
  code as a whole token of Name) is equivalent for PB2002 and avoids substring false hits.
