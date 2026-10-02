# Source & compilation notes — earthquake-plate-distance

## Provenance

This AIP skill was compiled from one curated Agent Skill bundled with the
`earthquake-plate-calculation` SkillsBench task:

- `ORIGINAL_SKILL.md` — verbatim copy of
  `vendor/skillsbench/tasks/earthquake-plate-calculation/environment/skills/geospatial-analysis/SKILL.md`.

The task itself (`instruction.md`, `solution/solution.py`, `task.toml`,
`environment/Dockerfile`, and the `PB2002_*.json` / `earthquakes_2024.json`
fixtures) was consulted for the concrete I/O contract — file paths under
`/root`, expected answer JSON keys, magnitude/place/time semantics, time
formatting to ISO 8601 UTC, and distance rounding — but its source files are
not copied here because they belong to the task, not the curated skill.

The `geospatial-analysis` curated skill is domain-general (any point-to-line
GeoPandas distance problem); this AIP compilation specialises it to the
plate-tectonics workflow the task exercises while keeping the target plate
and boundary filter parameterised via state inputs.

## Step-kind choices

The whole procedure is deterministic once the inputs are given, so it
compiles to one `execution` step plus `end`:

- **`find-furthest` (`execution`)** — every operation in the curated skill's
  "Common Workflow Pattern" (load, filter by polygon, project, union
  boundaries, compute distances, `nlargest`, convert time, write JSON) is
  pure code over declared inputs. No judgement, no free-form generation, no
  branching on a value that only a model can produce, so it is a single
  script per the AIP "Choose the Step Kind" guidance (deterministic
  if/then/else and numeric calculation → `execution`).
- **`end`** — declares the shape of the final state (`output_path`,
  `result`).

No `decision` step: the target plate is a caller-supplied string
(`plate_name` / `boundary_name_pattern`), not something the skill judges from
the data. No `client_task`: nothing needs to be generated — the answer is a
deterministic function of the inputs. No `router`: there is no branching.

## Line-by-line completeness check against ORIGINAL_SKILL.md

Walk of the curated skill; each item is either **carried** (where in this
skill it lives) or **deliberately dropped** (with rationale). Rules,
thresholds, lookups, branching, and context needed to apply them are never
deliberate drops.

- Description "Analyze geospatial data using geopandas with proper coordinate
  projections. Use when calculating distances between geographic features…" →
  carried into the skill's frontmatter `description` (specialised to
  earthquakes/plates but preserving the trigger keywords).
- License MIT → carried as `license: MIT` in frontmatter.
- "Geographic vs Projected Coordinate Systems" table (EPSG:4326 vs
  EPSG:4087, degrees vs metres) → the operative rule ("project to a metric
  CRS before distance") is carried in the `find-furthest` step description
  and in `anti_patterns`; the script hard-codes `METRIC_CRS = "EPSG:4087"`.
- "Critical Rule: Never calculate distances directly in geographic
  coordinates (EPSG:4326). Always project to a metric coordinate system
  first." → carried into `anti_patterns` and enforced in the script.
- "Why Projection Matters" incorrect-vs-correct code snippet → the rule it
  illustrates is carried; the illustrative snippet itself is a deliberate
  drop (documentation-only; the correct behaviour is executed by the
  script).
- "Loading Geospatial Data" — `gpd.read_file(...)` for plates and boundaries
  → carried in the script (`gpd.read_file(plates_path)` and
  `gpd.read_file(boundaries_path)`).
- "From Regular Data with Coordinates" — `Point(lon, lat)` + `GeoDataFrame`
  with `crs="EPSG:4326"` → carried in the script's earthquake loading
  (points constructed from `longitude, latitude`, CRS EPSG:4326).
- "Spatial Filtering — Finding Points Within a Polygon" using `.within()`
  and `.unary_union` → carried in the script: target plate polygon is built
  with `.unary_union` and earthquakes are filtered with `.within()`.
- "Using `.unary_union` for Multiple Geometries" — carried: the script
  unions the target plate polygon and the filtered boundary segments before
  distance calculation. Rule is called out in `anti_patterns`.
- "Distance Calculations — Point to Line/Boundary Distance" four-step
  recipe (load, project, union, distance/1000) → carried verbatim in the
  script and echoed in the step description.
- "Finding Furthest Point" using `.nlargest(1, "distance_km")` → carried
  literally in the script.
- "Common Workflow Pattern" full earthquakes-vs-plates example — this is
  the exact pipeline the skill executes. Every operation (load, build
  earthquake GeoDataFrame, filter by target plate polygon, project to
  metric CRS, filter boundary segments by name pattern, union, distance in
  km, `nlargest`) is carried by the script. The example's use of
  `Code == "PA"` for polygon selection is replaced by
  `PlateName == plate_name` because the PB2002 plates layer keys plate
  identity by `PlateName` (`Pacific`) while the boundaries layer keys by
  `Name` substrings like `PA`; both are parameterised via state inputs
  (`plate_name`, `boundary_name_pattern`) so the caller can point at any
  plate.
- "Filtering by Attributes" examples (`PlateName`, `Code`, `str.contains`,
  `PlateA/PlateB` pattern) → the two forms this skill actually uses are
  carried (`PlateName == plate_name` for the polygon selector,
  `Name.str.contains(boundary_name_pattern)` for the boundary selector).
  The other combinations (`Code`, `PlateA`/`PlateB` OR filter) are
  documentation-only alternatives and are a deliberate drop; agents who
  need them can consult `ORIGINAL_SKILL.md` under `source/`.
- "Performance Tips" — filter before projecting, project once, use
  `.unary_union`, `.copy()` when modifying → carried by the script's
  ordering (filter → project → union → distance) and by the `.copy()` on
  the filtered subset. Called out in `anti_patterns`.
- "Common Pitfalls" table — distance-in-degrees, antimeridian, slow
  boundary-per-point loops, missing geometries → the first three are
  carried in `anti_patterns` and enforced by the script. The
  "missing geometries" row is a deliberate drop: the PB2002 layers used by
  this task have complete geometries; adding a `gdf.geometry.notna()` guard
  would be defensive code without a real failure mode against these
  fixtures.
- "When NOT to Use Manual Calculations" — no Haversine, no manual
  point-in-polygon, no per-boundary-point iteration → all three are carried
  in `anti_patterns`.
- "Best Practices Summary" 1–9 — every operative rule is carried either in
  the step description (load, `.within()`, project to EPSG:4087, union,
  `.distance()`, `.nlargest()`) or in `anti_patterns` (no EPSG:4326
  distances, no manual Haversine, no per-vertex iteration).

## Deliberate drops (recap)

- Incorrect-example code snippets used purely to illustrate rules that are
  already carried and enforced (the "Why Projection Matters" wrong/right
  pair).
- Alternative-attribute examples the compiled pipeline does not use
  (`Code == "PA"`, `PlateA`/`PlateB` OR filter). The verbatim
  `ORIGINAL_SKILL.md` remains under `source/` for agents needing those
  alternates.
- `gdf[gdf.geometry.notna()]` missing-geometry guard — not needed for the
  PB2002 fixtures this workflow is built for; no failure mode to guard
  against here.

## Task-specific I/O contract

Confirmed against
`vendor/skillsbench/tasks/earthquake-plate-calculation/instruction.md` and
`solution/solution.py`:

- Fixed input paths in-container: `/root/earthquakes_2024.json`,
  `/root/PB2002_plates.json`, `/root/PB2002_boundaries.json`.
- Fixed output path: `/root/answer.json`.
- Answer keys: `id`, `place`, `time` (ISO 8601 `YYYY-MM-DDTHH:MM:SSZ` UTC),
  `magnitude` (from `props.mag`), `latitude`, `longitude`, `distance_km`
  rounded to 2 decimal places.
- Target plate: Pacific → `plate_name="Pacific"`,
  `boundary_name_pattern="PA"`.
