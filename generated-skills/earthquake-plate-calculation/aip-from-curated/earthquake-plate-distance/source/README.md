# Provenance

Compiled from one curated Agent Skill:

- `geospatial-analysis-SKILL.md` — the sole upstream skill. Copied
  verbatim from `inputs/skills/geospatial-analysis/SKILL.md` (MIT).

That skill is a general geopandas how-to for geographic distance work.
Its "Common Workflow Pattern" section walks through the exact workflow
this task needs: load earthquakes + plates + boundaries, filter
earthquakes to a plate, project to EPSG:4087, union the relevant
boundaries, compute per-earthquake distances, pick the extremum. The
AIP compilation collapses that pattern into one `execution` script plus
a thin request-parsing + answer-writing wrapper.

# Step-kind choices

- `parse-request` → `client_task`. The input is free-form user text; the
  mapping from "Pacific" to code `PA` and from "furthest / closest /
  average" to a `metric` label is simple natural-language work. A
  `decision` with a fixed choice set would also fit `metric` and
  `boundary_scope`, but `plate_code` is open-ended (54 PB2002 codes,
  plus synonyms like "Pacific Plate"), so a single client_task that
  returns all three keys together keeps the graph flat and avoids a
  three-step decision chain.
- `compute` → `execution`. The whole computation is deterministic
  geopandas: `read_file`, `.within`, `to_crs("EPSG:4087")`,
  `.unary_union`, `.distance`, `nlargest`/`nsmallest`/`mean`/`median`.
  Exactly the "scripting" case called out in the AIP best practices.
- `report` → `client_task`. Short natural-language synthesis of a
  pre-computed summary string plus structured numbers. No new judgment
  that the script could have made.
- `end` → carries `answer` (headline text) plus the key structured
  values (`distance_km`, `plate_code`, `metric`) so a caller that wants
  just the number does not have to parse prose.

# Deliberate drops (recorded, with rationale)

The upstream skill is a general geopandas tutorial. The following
sections of the source are not reproduced verbatim in the AIP body
because the compiled procedure already encodes the behavior they
prescribe. They remain in `source/geospatial-analysis-SKILL.md` and in
the `references/geopandas-cheatsheet.md` crib, so an agent that opens
either can see them.

- "Geographic vs Projected Coordinate Systems" table and "Why
  Projection Matters" example. The rule they teach — never
  `.distance()` on EPSG:4326 — is enforced by `scripts/compute_distance.py`
  (hardcodes `METRIC_CRS = "EPSG:4087"`) and restated in the
  `anti_patterns` block and in `references/geopandas-cheatsheet.md`.
- "Loading Geospatial Data → From Regular Data with Coordinates"
  (building a `GeoDataFrame` from a plain dict). The task's earthquake
  input is USGS GeoJSON, not a plain lat/lon table; the script's
  `load_earthquakes` handles that specific format directly. The generic
  pattern remains in the source file.
- "Spatial Filtering → Finding Points Within a Polygon" and
  ".unary_union" prose. Both are the exact pattern used in
  `scripts/compute_distance.py` (`gdf_eq[gdf_eq.within(plate_geom)]`,
  `bounds_subset.to_crs(METRIC_CRS).geometry.unary_union`).
- "Distance Calculations" and "Finding Furthest Point" worked examples.
  Encoded in the script, with the `metric` input choosing between
  `nlargest` / `nsmallest` / `mean` / `median`.
- "Filtering by Attributes" patterns. Encoded: the script filters
  plates by `Code == plate_code` and boundaries by
  `(PlateA == plate_code) | (PlateB == plate_code)`. The source
  example that uses `Name.str.contains("PA")` is called out as a
  pitfall (would also match `"PAC"` / `"PAN"` neighbors) in both the
  script's comment above the boundary filter and in
  `references/pb2002-plate-codes.md`.
- "Performance Tips" and "When NOT to Use Manual Calculations". The
  script already applies all four tips (filter before project; project
  once; `unary_union`; `.copy()`), and does not implement Haversine or
  manual point-in-polygon. Restated as `anti_patterns` entries.
- "Common Pitfalls" table. Reproduced in
  `references/geopandas-cheatsheet.md` as the "Pitfalls that bit prior
  runs" table, where an agent looks when the number is wrong.
- "Best Practices Summary" numbered list. All nine items are already
  enforced by the script or restated in anti_patterns / cheatsheet;
  reproducing the list verbatim in the SKILL.md body would be padding.

Nothing operational (loader behavior, projection choice, filter
semantics, aggregation choice, pitfall list) was dropped.

# One API adaptation vs. the source

The source skill teaches `gdf.geometry.unary_union` (the attribute).
On geopandas ≥ 1.0 that attribute emits a DeprecationWarning in favor
of the `.union_all()` method; both still work. The script and the
cheatsheet use `.union_all()` so stderr stays clean and the pack
survives the attribute's removal. Semantics are unchanged.

# How to run locally

```
# From the pack root (not here; this is the source/ folder)
uv venv --python 3.14 ../../scratch/venv
uv pip install --python ../../scratch/venv/bin/python geopandas shapely pyproj pandas numpy
PYTHONPATH="$(../../scratch/venv/bin/python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')" \
  aip run . --input ../../scratch/start.json
```

In the task's container, the three input files land in `/root/`
alongside the Dockerfile's installs; pass those paths in the start
input.
