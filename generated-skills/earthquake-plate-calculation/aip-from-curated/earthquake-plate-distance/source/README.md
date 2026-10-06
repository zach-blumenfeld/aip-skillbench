# Source and compilation notes — `earthquake-plate-distance`

## Provenance

Compiled from one curated Agent Skill:

- `geospatial-analysis/SKILL.md` — a general geopandas guide (`gpd.read_file`,
  CRS projection to `EPSG:4087`, `.within()` spatial filtering, `.distance()`
  with `.unary_union`, `.nlargest()` extremum picks) that uses the exact
  earthquake-near-plate-boundary workflow as its complete worked example.

The curated source is copied verbatim into `source/geospatial-analysis/`.

The runtime environment is a Python 3.12 container with `pandas==2.2.3`,
`numpy==1.26.4`, `geopandas==1.0.1`, `shapely==2.0.6`, `pyproj==3.7.0` and the
three PB2002 / earthquake JSON files mounted at `/root/` (see
`inputs/environment/Dockerfile`). The compiled skill assumes these packages are
available; it does not bootstrap them.

## Compilation target

The curated skill is procedural guidance for a human reader. The task class it
targets — "find the earthquake inside plate X that is furthest from (or
closest to) that plate's boundary" — is a single deterministic pipeline over
three well-known GeoJSON inputs. The compiled procedure therefore encodes the
whole pipeline as one script and uses the client only where the client is
unavoidable: parsing the user's natural-language request into typed
parameters, and summarising the numeric result back in prose.

## Step-kind choices

Per the AIP spec, step kinds are chosen in order: script → decision → client
task.

1. **`parse-request` (client_task).** The start step. Extracting a PB2002
   two-letter plate code, the extremum (`furthest` / `closest`), and a top-N
   count from a free-text request is open-ended natural-language work — not a
   lookup table and not a yes/no judgment, so neither `execution` nor
   `decision` fits. A `client_task` lets the agent map plate names
   (`"Pacific"`, `"Nazca"`, …) to codes using the mapping table carried in
   the template, pass the data-file paths through unchanged, and fall back to
   sensible defaults (`PA`, `furthest`, `1`) when the request is terse.
2. **`compute` (execution).** The whole geospatial pipeline — load three
   GeoJSON files, filter the target plate, spatially filter earthquakes with
   `.within()`, project to `EPSG:4087`, filter boundaries involving the plate,
   combine them with `union_all()`, compute `.distance()` in metres, convert
   to km, and pick the top-N by `nlargest` / `nsmallest` — is deterministic
   code over structured inputs. The spec says: when the logic can be written
   as code over the declared inputs, use `execution`. One script covers it;
   splitting into load / project / distance scripts would just add I/O without
   adding clarity.
3. **`report` (client_task).** The numeric top-N must become a short
   natural-language answer that mentions the leading earthquake's distance,
   coordinates, magnitude, and place. That is generation, not computation.
4. **`end`.** Declares the final-state shape (`summary`, `top_results`,
   `count_in_plate`, `plate_code`).

No `router` is needed — the pipeline is linear, and the extremum
(`furthest` vs `closest`) is handled as a parameter inside `compute` rather
than as a branch, since the two cases differ by one line of pandas code.

No `decision` is needed — the only categorical judgment (which plate the user
means) is one of a large open set of codes, not a small fixed label set, so
free-text extraction in the client task is the right fit.

## Line-by-line completeness check — curated → compiled

Walked `source/geospatial-analysis/SKILL.md` end to end. Each distinct piece
of guidance is either carried in the compiled skill (file + location below) or
listed as a deliberate drop with rationale.

| Source content | Where it lives in the compiled skill |
|---|---|
| `description` ("Analyze geospatial data … calculating distances … plate boundaries and earthquake data.") | Narrowed and sharpened in the compiled skill's `description` and `purpose`. |
| CRS table — EPSG:4326 geographic (degrees) vs EPSG:4087 projected (metres); use the metric CRS for distance | Enforced in `scripts/compute_earthquake_plate_distance.py` via the `METRIC_CRS = "EPSG:4087"` constant and the project-before-distance order of operations. Also stated verbatim in `references/geopandas-cheatsheet.md` so the agent reading the SKILL body sees why it matters. |
| "Never calculate distances directly in geographic coordinates (EPSG:4326). Always project to a metric coordinate system first." | Same — enforced in the script, restated in the reference. |
| Why-projection-matters incorrect/correct code example | `references/geopandas-cheatsheet.md`. |
| Loading GeoJSON with `gpd.read_file` | Script uses `gpd.read_file` for plates, boundaries, and (first-attempt) earthquakes. |
| Building a `GeoDataFrame` from lat/lon records with `Point(lon, lat)` and `crs="EPSG:4326"` | Script's `load_earthquakes` fallback path, for when `read_file` can't parse the earthquakes file as GeoJSON. |
| `.within(polygon)` spatial filtering | Script filters earthquakes to the target plate with `gdf_eq[gdf_eq.within(plate_geom)]`. |
| `.unary_union` for combining multiple geometries | Script uses `union_all()` (the geopandas-1.0 replacement) with a `.unary_union` fallback for older versions. |
| Filtering boundaries by `str.contains(code)` on `Name`, or by `PlateA == code \| PlateB == code` | Script's `filter_boundaries` tries both schemas (prefers `PlateA`/`PlateB`, falls back to `Name.str.contains`). |
| Four-step point-to-line distance workflow (load → project → union → distance in metres → ÷1000) | Script implements this in order; `assets/parse_request.md` and `references/geopandas-cheatsheet.md` describe it. |
| `.nlargest(n, "distance_km")` for furthest, by implication `.nsmallest` for closest | Script branches on `extremum` and uses `nlargest`/`nsmallest` accordingly. |
| Complete earthquake-near-plate-boundary worked example | Entire compiled pipeline. |
| Attribute filtering (`Code == "PA"`, `PlateName == "Pacific"`, `str.contains("PA")`) | Script's `filter_plate` tries code columns first, then name columns, case-insensitive substring. |
| Performance tips — filter before projecting, project once, use `.unary_union`, `.copy()` when modifying | All honoured in the compiled script. Noted in `references/geopandas-cheatsheet.md`. |
| Pitfalls table — distance-in-degrees, antimeridian, slow iteration, missing geometries | Enforced in the script (metric CRS, `union_all` single call, `gdf.geometry.notna()` filter). Antimeridian is handled implicitly by letting geopandas own the spatial ops. Restated in `references/geopandas-cheatsheet.md`. |
| "When NOT to use manual calculations" (no Haversine, no manual point-in-polygon, no iterating boundary points) | `anti_patterns` in the YAML body, plus the reference. |
| Best-practices summary (eight ✅/❌ bullets) | Collectively encoded as behaviour in the script and surfaced to the client via the reference. |

### Deliberate drops

Nothing operational was dropped. The items below are present in the curated
source but not re-stated in the compiled body — each is either background
exposition that the schema has no field for, or redundant with content that is
already carried.

- **The "Why Projection Matters" prose paragraph.** The *rule* ("project
  before measuring distance") is enforced in the script and restated in
  `references/geopandas-cheatsheet.md`. The paragraph of explanation is
  pedagogical background; the script does not need the agent to understand the
  derivation, only to follow the pipeline.
- **The alternative "from regular lat/lon dicts" loading snippet, in the
  common-workflow section.** The script already contains both code paths
  (GeoJSON first, lat/lon-dict fallback) and chooses between them at runtime,
  so the agent never has to replicate the snippet.
- **The `pacific_plate_alt` / `pa_related` variable-name variants in the
  "Filtering by Attributes" examples.** Variable names in example code are
  not instructions; the behaviour (match by code OR by name, boundaries
  involving a plate = match on `PlateA`/`PlateB` OR `Name` substring) is in
  the script.
- **The "Avoid: projecting large dataset just to filter" counter-example.**
  The positive version ("filter first, then project") is in the script and
  the reference; the negative framing is explanatory redundancy.
