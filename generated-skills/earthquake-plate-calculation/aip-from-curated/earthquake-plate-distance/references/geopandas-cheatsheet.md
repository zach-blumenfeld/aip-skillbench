# Geopandas / PB2002 cheatsheet

Load this reference if you need to debug `compute` output, decide whether to
revise the parsed parameters, or explain a surprising result. The invariants
below are the ones the pipeline enforces; if a user question collides with
one of them, trust the invariant.

## Coordinate systems — the one invariant that matters

| CRS | Role | Units |
|-----|------|-------|
| `EPSG:4326` (WGS84) | Storage, display, spatial filtering (`.within()`) | Degrees (lon/lat) |
| `EPSG:4087` (World Equidistant Cylindrical) | **Distance calculations** | Metres |

**Never calculate distances directly in EPSG:4326** — degrees are not equal
distances everywhere on Earth. Project to `EPSG:4087` first, measure in
metres, then divide by 1000 for kilometres. The compiled script does this
unconditionally; do not hand-roll Haversine formulas on top of the result.

## Pipeline the script runs

1. `gpd.read_file(plates_path)` → polygons, EPSG:4326.
2. `gpd.read_file(boundaries_path)` → lines, EPSG:4326.
3. Earthquakes: `gpd.read_file(earthquakes_path)` first; if that yields no
   geometry, parse the JSON manually and build `Point(lon, lat)` features in
   EPSG:4326.
4. Filter plates: match the requested PB2002 code against `Code` /
   `PlateCode`; fall back to substring match on `PlateName` / `Name`.
   `union_all()` the matching polygons.
5. `gdf_eq[gdf_eq.within(plate_geom)]` — spatial filter in EPSG:4326 before
   projecting (filter-then-project is faster and preserves data).
6. `to_crs("EPSG:4087")` on both the filtered earthquakes and the
   plate-relevant boundaries.
7. Filter boundaries: prefer the exact `(PlateA == code) | (PlateB == code)`
   match; fall back to substring on `Name`. `union_all()` the result into a
   single multi-line geometry.
8. `eq_proj.geometry.distance(boundary_geom)` returns metres; divide by 1000
   for `distance_km`.
9. `nlargest(top_n, "distance_km")` for `furthest`, `nsmallest` for
   `closest`.

## Non-obvious things worth knowing

- For a point strictly inside a plate, the nearest point on *any* global
  plate boundary lies on a boundary of *that* plate. Filtering boundaries by
  the plate code is an optimisation, not a correctness fix — but we keep it,
  because the filter also makes a wrong-plate error (`"XX"`) surface at the
  boundary-filter step rather than silently returning global distances.
- `union_all()` is the geopandas-1.0 method. Older code uses `.unary_union`;
  the script tries `union_all()` first with a `.unary_union` fallback.
- `.within()` on a FeatureCollection with mixed geometries can return
  `False` for points exactly on an edge. If `count_in_plate` is suspiciously
  low, the data is probably coarser than the request assumes — not a bug in
  the pipeline.
- Antimeridian: geopandas spatial operations handle it. Do not nudge
  longitudes by ±360 by hand.
- Missing geometries: the script drops `gdf.geometry.notna()` rows before
  filtering.
- PB2002 codes are case-sensitive in some column names; the script uppercases
  before comparing.

## When the script fails

- `No plate matched '<code>'` — the user named a plate the dataset does not
  carry under that code or substring. The error prints up to 30 identifiers
  from the plate layer; ask the user which one they meant.
- Everything else is a data-shape surprise (unexpected column names, empty
  earthquakes file). The script's stack trace is the source of truth.
