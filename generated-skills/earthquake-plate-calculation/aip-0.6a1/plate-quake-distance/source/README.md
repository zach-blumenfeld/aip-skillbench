# plate-quake-distance — source and provenance

## Provenance

- `geospatial-analysis/SKILL.md`: the curated Agent Skill "Geospatial Analysis with GeoPandas" (MIT), copied verbatim. It was the only file in the input skill folder, so there were no scripts, references, or assets to carry over.
- Task context (not copied, since it is task-specific): a downstream agent gets USGS 2024 M5+ earthquakes (`/root/earthquakes_2024.json`, a GeoJSON FeatureCollection with time in epoch ms and points as `[lon, lat, depth]`) and the PB2002 plate model (`PB2002_plates.json` polygons with `Code`/`PlateName`; `PB2002_boundaries.json` LineStrings with `Name`/`PlateA`/`PlateB`). It must write the Pacific-plate earthquake furthest from the Pacific plate boundary to `/root/answer.json`, using GeoPandas projections. The container is python:3.12-slim with pandas 2.2.3, numpy 1.26.4, geopandas 1.0.1, shapely 2.0.6, and pyproj 3.7.0.

## Intent

The skill compiles the source's GeoPandas workflow into a single deterministic script, so the agent does not re-derive it and fall into the traps the source warns about. The plate is a start input (code or name), so the same skill answers the question for any PB2002 plate and any earthquake file in the same format.

## Component-kind choices

| Step | Kind | Why |
|---|---|---|
| `analyze` | execution | Loading, `.within()` filtering, projecting to EPSG:4087, `.distance()` to the unioned boundary, and `nlargest` are all deterministic code over the inputs. That is the source's "Common Workflow Pattern". |
| `by-status` | router | Branches on the script's `status`. The only real fork is whether any event falls inside the plate. |
| `write-answer` | execution | Writing a fixed-field JSON file is deterministic. It is kept separate from `analyze` so nothing is written when there is no answer. |
| `diagnose-empty` | client_task | With zero in-plate events, the agent has to judge whether an input is wrong (wrong plate, swapped coordinates) or whether no event truly qualifies, and write that up. A script can't make that call. |
| `end` | end | Returns the status, the plate code, the in-plate count, and the `furthest` record. |

No decision step: nothing in the workflow needs a judgment against a fixed answer space.

`assets/config.json` holds the CRS choices (`EPSG:4326` source, `EPSG:4087` metric) and the top-N count for runner-up candidates. `references/geopandas-guide.md` keeps the source's explanatory material (CRS table, code pattern, performance tips, pitfalls) for when the agent has to deviate from the script.

## Decisions beyond the source (found during functional testing on the real files)

- **Boundary = boundaries-file segments, not the plate outline.** The Pacific polygon is a MultiPolygon split at ±180°. Its outline has artificial antimeridian edges, and measuring to the outline gives a much smaller distance for the Hawaii event than measuring to the PA boundary segments. Recorded as an anti-pattern and in the reference pitfalls table.
- **2-D points built from lon/lat in EPSG:4326.** The source's "From Regular Data with Coordinates" pattern is used. `gpd.read_file` on the USGS file returns 3-D points tagged EPSG:4979, so building 2-D points keeps the CRS exactly as the source prescribes.
- **Time conversion.** USGS `time` is epoch ms. pandas hands it back as numpy int64, which `pd.Timestamp` reads as nanoseconds (a 1970 date). The script converts through `datetime.fromtimestamp(ms // 1000, UTC)` and formats `YYYY-MM-DDTHH:MM:SSZ`, truncating sub-seconds.
- **PROJ version drift.** EPSG:4087 northings are spherical in PROJ 9.4.1 (pyproj 3.7.0 wheels, the container pin) and ellipsoidal in PROJ 9.8. The same event's distance differs by about 0.3%. The script reports `proj_version`, and an anti-pattern tells the agent not to "correct" the container's result against another environment.
- **`.union_all()`** replaces the source's `.unary_union`. Both exist in geopandas 1.0.1, but `.unary_union` is deprecated. The scripts run clean under `-W error` on the pinned stack.
- **Plate matching.** Plates are matched on `Code` or `PlateName`, case-insensitive. Boundaries are matched on `PlateA`/`PlateB` OR a `Name` token split on `-`, `/`, `\` (PB2002 uses all three, e.g. `AU\PA`). This is equivalent to the source's `Name.str.contains("PA")` for PA, and safe for any 2-letter code.

## Completeness check (source line by line → where it lives)

| Source content | Location in skill |
|---|---|
| Overview paragraph | `purpose` (deliberate condensation, see drops) |
| CRS table (EPSG:4326 geographic/degrees; EPSG:4087 projected/metres) | `assets/config.json`; reference "Coordinate systems" |
| Critical rule: never compute distance in EPSG:4326 | anti_patterns[0]; `analyze.py` projects before `.distance()`; reference |
| "Why projection matters" ❌/✅ code, `/1000.0` to km | `analyze.py`; reference |
| Load GeoJSON with `gpd.read_file` | `analyze.py` (plates, boundaries); reference pattern |
| GeoDataFrame from coordinate records (`Point(lon, lat)`, crs 4326) | `analyze.py` `load_earthquakes` (FeatureCollection and list-of-records forms) |
| Spatial filtering: plate polygon by name, `.unary_union`, `.within()`, count found | `analyze.py` `resolve_plate` + `.within()`; `n_in_plate` output |
| `.unary_union` to combine boundary segments; `Name.str.contains("PA")` | `analyze.py` `plate_boundaries` + `union_all()`; reference note on equivalence |
| Point-to-boundary distance steps 1–4 | `analyze.py` |
| Furthest point: `nlargest(1, ...)`, print id and distance to 2 dp | `analyze.py` (`furthest`, `top_candidates`, distance rounded to 2 dp) |
| Common Workflow Pattern (load → GeoDataFrame → filter by `Code == "PA"` → project → PA boundaries → distance → nlargest) | `analyze.py` end to end; `write-answer` |
| Filtering by attributes: `PlateName == "Pacific"`, `Code == "PA"`, `PlateA/PlateB == "PA"`, `str.contains` | `resolve_plate` (code or name), `plate_boundaries` (PlateA/PlateB or Name) |
| Performance tip 1: filter before projecting | `analyze.py` projects only in-plate events; anti_patterns; reference |
| Performance tip 2: project once | `analyze.py`; reference |
| Performance tip 3: unary_union before distance | `analyze.py`; anti_patterns; reference |
| Performance tip 4: `.copy()` filtered frames | `analyze.py` (`inside = ...copy()`); anti_patterns; reference |
| Pitfall: distance in degrees | anti_patterns[0]; reference |
| Pitfall: antimeridian / manual ±360 | anti_patterns (manual shifts; polygon-outline trap); reference |
| Pitfall: slow per-point distances | anti_patterns; reference |
| Pitfall: missing geometries → `notna()` | `analyze.py` skips features without point coords; filters plates/boundaries `geometry.notna()`; reference |
| When NOT to use manual calcs (Haversine, point-in-polygon, iterating boundary points) | anti_patterns; reference |
| Best Practices Summary 1–9 | Each item already covered by the rows above |
| `license: MIT` | frontmatter `license` |
| Frontmatter description keywords (geopandas, projections, distance, spatial filtering, plate boundaries, earthquakes) | `description`, `trigger_when` |

## Deliberate-drop log

- **Overview prose** ("provides accurate distance calculations… this guide covers best practices"): framing only, condensed into `purpose`.
- **`print(...)` lines in the examples** (found-count, furthest id/distance): diagnostic console output, replaced by typed outputs (`n_in_plate`, `furthest`, `top_candidates`).
- **The "Avoid: projecting large dataset just to filter" counter-example code**: redundant with performance tip 1, which is kept as behaviour and as an anti-pattern.
- **Generic placeholder file names** (`points.json`, `plates.json`, `boundaries.json`): illustrative only. Real paths are start inputs.
