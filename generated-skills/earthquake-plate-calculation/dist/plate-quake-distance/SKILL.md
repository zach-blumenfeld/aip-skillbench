---
name: plate-quake-distance
description: Find the earthquake inside a tectonic plate that lies furthest from (or closest to) that plate's boundaries, using GeoPandas with a projected metric CRS (EPSG:4087). Use for USGS earthquake GeoJSON plus PB2002 plate polygons/boundaries tasks — point-in-plate filtering, point-to-boundary distance in km, and writing the winning event (id, place, ISO time, magnitude, lat/lon, distance_km) to JSON.
license: MIT
compatibility: Python >= 3.10; pip packages geopandas>=0.14 (tested 1.0.1), shapely>=2.0, pyproj, pandas. No network needed.
---

# Plate Quake Distance

## Trigger When

- A task asks for the earthquake furthest from / closest to a plate boundary within a plate (e.g. "furthest from the Pacific plate boundary within the Pacific plate").
- Inputs are a USGS earthquake GeoJSON FeatureCollection plus the PB2002 plates (polygons) and boundaries (line segments) GeoJSON files.
- Any point-to-line distance or point-in-polygon filter over lat/lon data where "use GeoPandas projections" is required.

## Purpose

Carries the exact GeoPandas recipe for plate/earthquake distance questions: build 2D points in EPSG:4326, filter with `.within()` the unioned plate polygon, select the plate's boundary segments, project both to the metric EPSG:4087, take one `.distance()` to the unioned boundary, and pick the extreme with `nlargest`/`nsmallest`. It adds the PB2002 field conventions, the USGS time/ID conventions, and the pitfalls (degrees-as-distance, antimeridian, Z coordinates) an agent would otherwise get wrong.

## Procedure

### 1. Read the task (client_task)

Read the task statement. Note the input paths, the output path, and the required output fields. Then answer decision 2.

### 2. Pin the parameters (decision)

```yaml
target_plate:
  type: choice
  instructions: Which plate does the task restrict earthquakes to and measure boundary distance for? Pass the label as --plate (Code or PlateName both work).
  criteria:
    PA: Pacific plate (the usual case).
    other: Any other PB2002 plate; pass its Code (e.g. NA, AU) or PlateName as given in the plates file.
extreme:
  type: choice
  instructions: Does the task want the largest or the smallest boundary distance?
  criteria:
    furthest: "furthest", "largest distance", "most distant", "deepest in the plate interior".
    closest: "closest", "nearest", "smallest distance" to the boundary.
crs_override:
  type: noul
  instructions: Does the task explicitly name a projected CRS other than EPSG:4087 for the distance calculation?
  criteria:
    true: The task names a specific EPSG code or projection to use for distances.
    false: The task only says to use projections / GeoPandas, or says nothing about CRS.
```

A wrong `crs_override: true` changes every distance; reconsider any close call that leans yes. "Use GeoPandas projections" alone is `false` → EPSG:4087.

### 3. Compute (execution)

Before the first run, check that `python3` is >= 3.10 and imports `geopandas`, `shapely`, `pyproj`, `pandas`; name everything missing. (The task container python:3.12-slim already has geopandas 1.0.1, shapely 2.0.6, pyproj 3.7.0, pandas 2.2.3.)

Run from the skill folder:

```bash
python3 scripts/plate_quake_distance.py \
  --earthquakes /root/earthquakes_2024.json \
  --plates /root/PB2002_plates.json \
  --boundaries /root/PB2002_boundaries.json \
  --plate PA --mode furthest --out /root/answer.json
```

- `--plate` ← `target_plate`; `--mode` ← `extreme`; add `--crs EPSG:XXXX` only if `crs_override` is `true`. `--top N` changes how many ranked candidates are printed (default 5).
- stdout is the answer JSON (also written to `--out`); stderr has counts, the ranked candidates, warnings.
- Output fields: `id` (USGS feature id, e.g. `us6000m30y`), `place`, `time` (UTC `YYYY-MM-DDTHH:MM:SSZ` from epoch ms), `magnitude` (`mag`), `latitude`/`longitude` (from the GeoJSON geometry, full precision), `distance_km` (rounded to 2 decimals).
- Accepts a GeoJSON FeatureCollection or a plain JSON list of records with `latitude`/`longitude` (or `lat`/`lon`) and `mag`/`time` fields.

What the script does (the method from the source skill; keep it if you ever reimplement):
1. Earthquakes → `Point(lon, lat)` in EPSG:4326 (depth dropped; `gpd.read_file` would give 3D EPSG:4979 points).
2. Plate rows matched on `Code` or `PlateName` (case-insensitive), unioned (`union_all()`, the non-deprecated `.unary_union`); keep quakes `.within()` it, in EPSG:4326. Rows with missing geometry are dropped.
3. Boundary segments with `PlateA == code` or `PlateB == code`, cross-checked against `Name` tokens (separators `-`, `/`, `\`, e.g. `PA-NA`, `NA/PA`, `AU\PA`); on mismatch it warns and uses the union. Uses the boundaries file, not the plate polygon outline: PB2002 polygons are cut at ±180°, so their outline contains fake edges along the antimeridian.
4. Project points and boundaries once to EPSG:4087 (metres), union the boundary segments, one `.distance()` call, ÷1000 → km, then `nlargest(1)` / `nsmallest(1)`.

### 4. Check the result (client_task)

- Exit 1 with `ERROR:` means: plate not found (the message lists valid Codes/PlateNames — pick the right one and rerun), no earthquakes within the plate, or no boundary segments for the code. Fix the argument; do not hand-compute.
- `WARNING: PlateA/PlateB selects ... Name selects ...`: the boundary file's fields disagree; the union is used, which is the right default. Mention it.
- `NOTE: across the antimeridian ...`: EPSG:4087 is cut at ±180°, so the winner's plain projected distance ignores a closer boundary on the other side. Keep the reported plain-projection value (that is what "use GeoPandas projections" computes), and mention the note.
- Sanity-check the winner: it must lie inside the plate (e.g. Hawaii and open-ocean events for the Pacific plate's interior) and the distance should be hundreds to thousands of km for "furthest", near 0 for "closest".
- Confirm the output file holds exactly the fields the task asked for.

## Gotchas

| Issue | Wrong | Right |
|---|---|---|
| Distance in degrees | `.distance()` in EPSG:4326 | Project to EPSG:4087 (metres) first, ÷1000 for km |
| Manual math | Haversine, hand point-in-polygon, looping over boundary vertices | `.within()`, `union_all()` + a single `.distance()` |
| Antimeridian | Adding ±360 to longitudes by hand | Use GeoPandas operations; read the script's antimeridian NOTE |
| Boundary choice | Outline of the plate polygon (has fake ±180° edges) | Boundary segments involving the plate's code |
| Performance | Projecting everything, then filtering | Filter (within plate, boundary subset) first, project once |
| Time format | Raw epoch ms or local time | UTC `YYYY-MM-DDTHH:MM:SSZ` |
