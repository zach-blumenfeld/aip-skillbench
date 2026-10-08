# Source and provenance: earthquake-plate-distance

## Provenance

- `geospatial-analysis/SKILL.md`: the curated Agent Skill "Geospatial Analysis with GeoPandas"
  (MIT), copied here unchanged. It was the only file in the curated input set, with no scripts,
  references or assets.
- Environment facts came from the task's environment folder: the Dockerfile (python:3.12-slim
  with pandas 2.2.3, numpy 1.26.4, geopandas 1.0.1, shapely 2.0.6, pyproj 3.7.0; inputs copied to
  `/root/earthquakes_2024.json`, `/root/PB2002_plates.json`, `/root/PB2002_boundaries.json`) and the
  first 2 KB of each input file:
  - earthquakes: a single-object USGS FeatureCollection (`metadata.count` = 1504). Features are
    `{"type","properties","geometry","id"}`. `geometry.coordinates` = `[lon, lat, depth_km]`.
    `properties.time` is epoch ms. `mag`, `place`, `magType` and `type` are in `properties`.
  - plates: a FeatureCollection of `Polygon`s. Properties are `LAYER`, `Code` (e.g. `AF`) and `PlateName` (e.g. `Africa`).
  - boundaries: a FeatureCollection of `LineString`s. Properties are `LAYER`, `Name` (`AF-AN`),
    `Source`, `PlateA`, `PlateB` and `Type`. One plate pair can have several segments, and the two
    codes appear in either order (`AF-AN`, `AN-AF`).

## Intent

The curated skill teaches the general method. The task family it serves is "find the earthquake
inside plate X that is furthest from that plate's boundary". This pack turns that worked example
into one script, so the agent only has to read the request and format the answer.

## Step-kind choices

| Step | Kind | Why |
|---|---|---|
| `classify-request` | decision | Two judgments with a fixed answer space: furthest or nearest, and whether to measure to the plate's own boundaries or to all boundaries. Typed answers feed the script. Thresholds are set so an ambiguous "any boundary" wording gets a second look. |
| `frame-request` | client_task | Pulling file paths, the plate, explicit filters and the verbatim output spec out of free text is extraction and generation. It also has to locate files in the container (`/root`). |
| `compute-distance` | execution | The whole geopandas method is deterministic: load, resolve the plate, `.within()`, select boundaries, project to EPSG:4087, union, `.distance()`, then nlargest/nsmallest. Scripting it enforces every "critical rule" in the source and removes the classic mistakes (degrees as distance, lat/lon swap, per-vertex loops). |
| `write-answer` | client_task | The output format (key names, file path, rounding) varies by task, so the agent has to produce it. The values themselves come from the script and are not recomputed. |
| `end` | end | Requires the answer object and the output path; the script result stays in the state. |

There is no router. The two decision answers are parameters of one computation, not different
procedures.

## Completeness map (source line → where it lives)

| Source content | Location in pack |
|---|---|
| Overview: use geopandas plus proper projections | `purpose`. The script implements it. |
| CRS table: EPSG:4326 is for storage and display; EPSG:4087 (metres) is for distances | Script constants `GEO_CRS` and `METRIC_CRS`. `references/geopandas-method.md`. |
| Critical rule: never take distances in EPSG:4326, project first | Script step 5. First `anti_patterns` entry. Reference rules. |
| "Why projection matters" example: distance in degrees vs metres, /1000 for km | Script (`/ 1000.0`). Anti-pattern. Reference snippet. |
| Load GeoJSON with `gpd.read_file` | Script (plates and boundaries). Earthquakes are parsed with `json` so the USGS `id`, depth and every property survive; see the drop log. |
| Build a GeoDataFrame from records with `Point(lon, lat)`, crs EPSG:4326 | Script `load_earthquakes` (it also accepts a plain list of lat/lon records). Lat/lon-swap anti-pattern. |
| Spatial filtering: `.within(target_poly)` with `unary_union` over the plate's polygons | Script `resolve_plate` takes every feature with the code, unions them, then calls `.within()`. |
| Use `.unary_union` to combine boundary segments | Script `union()`: `union_all()` on geopandas ≥ 1.0, falling back to `unary_union`. |
| Point-to-boundary distance workflow (steps 1–4) | Script `main`. |
| Finding the furthest point with `nlargest(1)` | Script picks nlargest or nsmallest according to `extreme`. A compact top 5 goes in `ranking`. |
| Common workflow: plate `Code == "PA"`, boundaries `Name.str.contains("PA")` | Script `resolve_plate` and `select_boundaries`. The substring match is replaced by an equivalent PlateA/PlateB match or a whole-token Name match; see the drop log. |
| Filtering by attributes: `PlateName`, `Code`, `PlateA`/`PlateB`, `str.contains` | Script resolves the plate by Code or PlateName (case-insensitive, and tolerates "the … plate"). Boundaries are selected by PlateA/PlateB plus Name tokens. `references/pb2002-plate-codes.md` covers aliases. |
| Performance: filter before projecting | The script calls `.within()` and the boundary selection in EPSG:4326, then projects only the subset. Anti-pattern. |
| Performance: project once | One `to_crs` for points and one for boundaries. Anti-pattern. |
| Performance: use `.unary_union` | Script. |
| Performance: `.copy()` filtered frames | Script (`inside = ...copy()`). Reference rules. |
| Pitfall: distance in degrees | Anti-pattern. Script. |
| Pitfall: antimeridian, don't shift longitudes by ±360 | Anti-pattern. Reference rules. The script uses the geometries as published. |
| Pitfall: slow per-boundary-point distance | Union plus one `.distance()` call in the script. Anti-pattern. |
| Pitfall: missing geometries, filter `notna()` | Script drops null or empty plate and boundary geometries, and skips earthquakes without coordinates (reported in `warnings`). |
| Avoid manual Haversine, point-in-polygon, and iterating boundary points | Anti-pattern. Reference rules. |
| Best-practices summary 1–9 | All covered by the rows above. |

## Additions beyond the source (from the environment and task family)

- Plate resolution errors list the available `Code=PlateName` pairs so the agent can self-correct.
- Optional request filters (magnitude, time window, event type) are applied only when the request
  states them.
- When GEOS refuses the published plate polygon, it is repaired with `buffer(0)`. Otherwise it is
  used as is, as in the source. A non-valid polygon is reported in `warnings`.
- Near-ties (within 10 m) are flagged.
- The output-writing rules: exact key names, keep full precision, write and read back the file.

## Deliberate-drop log

| Dropped | Rationale |
|---|---|
| The `Name.str.contains("PA")` substring match, used literally | It is redundant with the PlateA/PlateB match, and a substring can hit unrelated codes. A whole-token Name match is kept as a fallback, so the PB2002 segment set is the same. On the synthetic test data both selections gave the same winner. |
| `gpd.read_file` for the earthquake file | Whether `read_file` keeps the USGS file's top-level feature `id` depends on the I/O driver. Parsing with `json` keeps the event id, the depth and every property. The geometry and CRS are the same. |
| Explanatory prose ("Why projection matters" narrative, "these manual approaches are slower…") | Rationale only. The rules it supports are in the script and `anti_patterns`. |
| Generic example records (`{"id": 1, "lat": 35.0, ...}`) and `print` statements | Illustrative only. They are replaced by the real USGS loader and structured output. |
| Region-filter example (`gdf_large["region"] == "Pacific"`) | Illustrative of "filter before project", which is kept. The column does not exist in these inputs. |

## Known limitation (kept on purpose)

EPSG:4087 is a planar projection. Distances measured across the antimeridian are not wrapped:
a point at −170° is about 320° of projected longitude from a line at 150°. The source skill
prescribes exactly this method (EPSG:4087, no manual longitude shifts), so the pack keeps it
rather than switching to geodesic distances. Distance values also shift slightly between PROJ
releases. With the container's pinned pyproj 3.7.0 the synthetic test winner was unchanged but
`distance_km` differed by about 0.4% from a newer pyproj, so always run the script inside the task
container.
