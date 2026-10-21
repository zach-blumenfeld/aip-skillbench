# Source and provenance: plate-quake-distance

## Provenance

- `geospatial-analysis/SKILL.md`: the curated source skill ("Geospatial Analysis with GeoPandas", MIT), copied verbatim. It was the only file under `inputs/skills/`.
- Task context, used for intent and testing but not copied: the task statement (find the earthquake within the Pacific plate furthest from the Pacific plate boundary, use GeoPandas projections, write `/root/answer.json` with id/place/time/magnitude/latitude/longitude/distance_km), and the container Dockerfile (python:3.12-slim, geopandas 1.0.1, shapely 2.0.6, pyproj 3.7.0, pandas 2.2.3, numpy 1.26.4).
- Input facts checked against the real files: the USGS FeatureCollection has 1504 Point features with string `id`, epoch-ms `time`, and `[lon, lat, depth]` coordinates. In PB2002 plates, the Pacific plate is one MultiPolygon (`Code` PA, `PlateName` Pacific) split at ±180°. PB2002 boundaries have 241 LineStrings with `Name`, `PlateA`, `PlateB`; 48 involve PA, and `PlateA`/`PlateB` agree with the `Name` tokens.

## Component-kind choices

| Component | Kind | Why |
|---|---|---|
| 1. Read the task | client_task | The agent has to read the task statement it was given; a script can't. |
| 2. target_plate / extreme / crs_override | decision (choice, choice, noul) | Pulling these from free-text instructions is a judgment, but the answers form a small fixed set, and the script takes them as arguments. |
| 3. Load, filter, project, measure, pick, format | execution (`scripts/plate_quake_distance.py`) | Deterministic geometry and formatting over fixed inputs: CRS choice, within-filter, boundary selection, distance, nlargest/nsmallest, ISO time, rounding. One script because the steps form one pipeline. |
| 4. Check result | client_task | Reading warnings and errors and sanity-checking the winner against the task means interpreting free text. Each error message names its fix. |

## Deliberate drops and adaptations

- **Dropped: the "Overview" paragraph.** It is background with no action in it.
- **Dropped: the illustrative code snippets** (Why Projection Matters, Loading, From Regular Data, Spatial Filtering, Distance Calculations, Finding Furthest Point, Common Workflow, Filtering by Attributes, Performance Tips). The script carries out every one of them. SKILL.md step 3 lists the method in 4 lines, and the Gotchas table keeps every do/don't.
- **Adapted: `Name.str.contains("PA")` became an exact token match on `Name` (split on `-`, `/`, `\`), unioned with `PlateA`/`PlateB == code`.** A substring match would also hit codes that contain the target (for example, "PA" inside a hypothetical "PAX"). On PB2002 the two selections are identical (48 segments for PA), so results are unchanged. When the fields disagree, the script prints a warning.
- **Adapted: `.unary_union` became `union_all()`**, with a fallback to `.unary_union`. `.unary_union` is deprecated in geopandas 1.0, and the result is identical.
- **Adapted: earthquakes are loaded with `json` + `Point(lon, lat)`, not `gpd.read_file`.** `read_file` returns 3D EPSG:4979 points. The source's "From Regular Data with Coordinates" pattern gives 2D EPSG:4326 points, which is the source's intent.
- **Clarified: the antimeridian pitfall.** The source says GeoPandas operations "handle it". That holds for `.within()` against the split MultiPolygon. EPSG:4087 distances, however, are cut at ±180°. The skill keeps the source method (plain projected distance) for the answer. The script adds a diagnostic NOTE when a shifted copy of the boundary is closer, and the skill warns against using the plate polygon outline, whose fake ±180° edges would distort distances. The source's rule against manual ±360 adjustments is kept.
- **Added, beyond the source:** the task's output-field conventions (UTC ISO time from epoch ms, `distance_km` rounded to 2 decimals), and a `closest` mode that covers the source's `.nsmallest()` mention.

## Functional test (done in the authoring session, with a venv pinned to the container's packages)

- Real inputs, `--plate PA --mode furthest`: 107 of 1504 quakes fall within PA, 48 boundary segments are used, exit 0, and the answer JSON is written. The ranking matched an independent ad-hoc GeoPandas computation.
- `--plate pacific --mode closest`: the name resolves case-insensitively and the smallest-distance event is returned.
- `--plate NA`: reaches the antimeridian NOTE branch.
- Unknown plate, and a quake file with none inside PA: both exit 1 with an actionable `ERROR:`.
- Variant instance (a list-of-records quake file with ISO+offset times and the top event removed; a boundaries file with one `PlateB` blanked): reaches the PlateA/PlateB-vs-Name WARNING branch, converts times to UTC, and returns the next-furthest event.
