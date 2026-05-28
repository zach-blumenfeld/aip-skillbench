# geospatial-analysis — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill `geospatial-analysis` (the
`aip-from-curated` track for the `earthquake-plate-calculation` task). The
canonical original is preserved verbatim at `source/ORIGINAL_SKILL.md`. The
curated skill shipped no code, so a helper module
`scripts/geo_ops.py` was authored to back the procedure steps.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md`.
- `source/procedure.schema.json` — the AIP `procedure` schema (v0.3a2) the
  body validates against. Bundled locally so the skill is self-contained.
- `scripts/geo_ops.py` — new helper module, written to encode the
  prose-only rules from the original (project before measuring, union
  before measuring, copy on filter, metre→kilometre conversion).

## Schema choice

`procedure` schema (reused, not drafted). The curated skill is a small
execution graph for geospatial reasoning: load → filter → measure →
select. That maps cleanly onto script-backed step nodes connected by
inputs / outputs.

## Why a helper script was added

The curated `SKILL.md` is prose only — no `scripts/` directory. The bulk
of its content is rules that are best enforced in code, not prose:

- "Never call `.distance()` in EPSG:4326" (silently returns degrees).
- "Project to a metric CRS before distance work."
- "Use `.unary_union` to combine multi-feature targets."
- "Divide metres by 1000 for kilometres."
- "Use `.copy()` after filtering so adding columns does not raise."
- "Drop missing geometries before unioning."

Per AIP best practice (steps with calculations, lookups, or numeric
thresholds belong in scripts), these rules were lifted into
`geo_ops.py`. The body now describes the graph; the helper enforces the
discipline. The remaining prose in the step descriptions covers what the
helper cannot know — *which* attribute mask to pass for a given task
(e.g. `Code == "PA"` vs `Name.str.contains("PA")` vs
`PlateA == "PA" | PlateB == "PA"`).

## Source-content classification (completeness check)

- "Overview" + "Why projection matters" → **Mapped** to `purpose` and the
  step descriptions for `compute-distance-to-target`.
- "Geographic vs Projected" table (EPSG:4326 storage, EPSG:4087 metric)
  → **Mapped**: encoded as constants in `geo_ops.py`
  (`STORAGE_CRS`, `METRIC_CRS`) and called out in the `compute-distance-to-target`
  description.
- "Loading Geospatial Data" — `gpd.read_file`, `Point` + `GeoDataFrame`
  construction → **Mapped** to `load-geospatial-data` step backed by
  `load_geojson` and `points_from_records`.
- "Spatial Filtering" — `.within` + `.unary_union` → **Mapped** to
  `spatial-filter` step backed by `filter_points_within`.
- "Distance Calculations" — project + unary_union + `.distance()` + /1000
  → **Mapped** to `compute-distance-to-target` step backed by
  `distance_km_to`.
- "Finding Furthest Point" — `nlargest` + `.iloc[0]` → **Mapped** to
  `select-extreme-point` backed by `extreme_by_distance`, plus an
  `anti_pattern` reminding callers to use `.iloc[0]` for a Series.
- "Common Workflow Pattern" (end-to-end earthquake/plate example) →
  **Mapped** to the first `scenario`.
- "Filtering by Attributes" (`PlateName == "Pacific"`, `Code == "PA"`,
  `PlateA | PlateB`, `str.contains`) → **Mapped** through the `where`
  parameter on the helpers and surfaced explicitly in step descriptions
  and `scenarios`.
- "Performance Tips" (filter before projecting, project once, unary_union,
  copy when modifying) → **Mapped** to a `scenario` (filter-before-project),
  step descriptions, and `anti_patterns`. The `.copy()` rule is enforced
  inside `filter_points_within`.
- "Common Pitfalls" table → **Mapped** to `anti_patterns` (distance in
  degrees, antimeridian, per-segment iteration, missing geometries).
- "When NOT to Use Manual Calculations" (Haversine, point-in-polygon,
  per-point boundary loops) → **Mapped** to `anti_patterns`.
- "Best Practices Summary" — the eight-point recap → **Mapped** across
  step descriptions, `scenarios`, and `anti_patterns`; nothing dropped.
- Example file names (`plates.json`, `boundaries.json`) → **Deliberate
  drop** of literal names. Generalized to "GeoJSON / geopandas-readable
  file" so the skill is portable; the actual paths are task-specific.

## On `do_not_use_when`

The original skill does not call out non-applicability. Two were added:
data without geographic coordinates (the helpers won't do anything
useful) and antipodal / continent-spanning measurements (EPSG:4087's
equidistant-along-meridians property degrades east-west away from the
equator; a region-appropriate CRS such as a local UTM zone fits better
there). These calibrations help the agent pick a different tool when
the assumption fails.
