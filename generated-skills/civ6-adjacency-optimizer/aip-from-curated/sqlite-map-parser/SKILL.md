---
name: sqlite-map-parser
description: Parse SQLite databases into structured JSON data. Use when exploring unknown database schemas, understanding table relationships, and extracting map data as JSON. Designed for SQLite-backed map files (e.g., Civ6 .Civ6Map) where tile/feature/resource tables share a linear ID and a single-row metadata table supplies grid width/height.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.11+ and the standard-library `sqlite3` module.
---

```yaml
purpose: >
  Parse SQLite databases into structured JSON by first introspecting the
  schema (tables, columns, primary/unique/foreign keys, indexes, row
  counts, samples), then planning the extraction shape from the discovered
  relationships, and finally emitting either an ordered array or a
  key-indexed map. Designed for unknown or semi-known schemas — Civ6
  .Civ6Map files in particular, where tile data is keyed by a linear ID
  and grid dimensions live in a single-row metadata table.

trigger_when:
  - User asks to extract data from a SQLite database into JSON.
  - Working with a .Civ6Map file (SQLite-backed) and need tile, terrain, feature, or resource data.
  - Exploring an unfamiliar SQLite database — table layout and relationships not yet known.
  - Need to decode spatial / grid-shaped data encoded with a linear ID (id → x, y).
  - Joining a main entity table with auxiliary feature/resource/lookup tables.

do_not_use_when:
  - The schema is already well-known, stable, and a hand-written extractor exists — call it directly.
  - The source is not SQLite (CSV/JSON/Excel/binary export) — use the appropriate parser.
  - You only need the schema for diagnostic purposes — use sqlite3 CLI's `.schema` and stop.

scope_and_approval: >
  Read-only on the source DB. Scripts open the database without WAL or
  write transactions and never issue DDL/DML. Writes go only to the agent-
  supplied `--out` paths for the schema report, the extraction plan, and
  the final JSON. No approval gate needed.

steps:
  - name: explore-schema
    description: >
      Introspect the database — for every user table emit columns/types,
      primary key, indexes (including UNIQUE constraints), foreign keys,
      row count, and a 3-row sample. Always run this first; never query
      tables before you know their shape.
    script: scripts/explore_schema.py
    inputs:
      - name: db-path
        type: string
        description: Path to the SQLite database file (e.g., a .Civ6Map).
    outputs:
      - name: schema-report
        type: object
        description: >
          { "db_path": ..., "tables": [{ "name", "columns", "primary_key",
          "indexes", "foreign_keys", "row_count", "sample_rows", ... }] }

  - name: identify-relationships
    description: >
      Read the schema report and decide: (a) the main entity table —
      usually the largest by row count with a PK on a stable ID; (b)
      auxiliary tables joining on that ID (FKs help but are often absent —
      a shared column name is enough); (c) lookup/enum tables (small
      `*Types` tables with a code→name mapping); (d) the metadata/config
      table (single row, holds `Width`/`Height` for grid data). If the
      main table's row count is close to `Width * Height`, key the output
      by (x, y) using `x = id % width; y = id // width` — verify `MIN(ID)`
      to confirm 0-indexed vs 1-indexed. When in doubt about a pattern,
      read references/common-patterns.md.
    inputs:
      - name: schema-report
        type: object
    outputs:
      - name: extraction-plan
        type: object
        description: >
          JSON consumed by scripts/extract_to_json.py. Required:
          `main_table`. Optional: `id_column` (default "ID"), `key_kind`
          ("id" or "xy"), `metadata_table`, `width_column`,
          `height_column`, `container_key`, `joins` (list of
          {table, on, fields}), `lookups` (list of {table, key, value,
          for_field}). See references/common-patterns.md for plan fragments.

  - name: extract-to-json
    description: >
      Execute the plan — load the main table indexed by its natural key,
      LEFT-JOIN auxiliary tables (preserving every main row), resolve
      lookups in place, and pull metadata from the config table. Missing
      join/lookup tables emit a stderr warning and are skipped, not fatal.
    script: scripts/extract_to_json.py
    inputs:
      - name: db-path
        type: string
      - name: extraction-plan
        type: object
    outputs:
      - name: extracted-json
        type: object
        description: '{ "metadata": {...}, "<container_key>": list_or_map_of_items }'

  - name: choose-output-shape
    description: >
      Pick the container shape. Default to array; switch to map only when
      downstream code does random-access lookups by natural key.
    inputs:
      - name: extracted-json
        type: object
    outputs:
      - name: final-json
        type: object
    one_of:
      - Array of objects with explicit key fields (default; pass --shape array).
      - Map keyed by natural ID or "x,y" string (pass --shape map).

  - name: spot-check
    description: >
      Sanity-check the final JSON against the source DB. Compare item
      counts to the main-table row count, verify distinct values on any
      resolved lookup field (e.g., terrain types), and sample 2-3 rows
      to confirm coordinate math and join attribution. Catches silent
      join-loss, lookup misses, and off-by-one coordinate errors.
    script: scripts/sample_table.py
    inputs:
      - name: db-path
        type: string
      - name: final-json
        type: object
    outputs:
      - name: sanity-report
        type: object

modes:
  - name: explore-only
    body: >
      Run `explore-schema` and stop. Use when the agent needs the schema
      map for planning or to ask the user which tables to extract.
  - name: full-extract
    body: >
      Run all five steps: explore → identify → extract → choose shape →
      spot-check. Default for end-to-end extraction.

scenarios:
  - need: Convert a Civ6 .Civ6Map file into a tile array for adjacency analysis.
    context: >
      explore-schema reports `Map` (1 row; Width=44, Height=26), `Plots`
      (1144 rows; PK=ID; columns include TerrainType, IsCoastal, IsRiver),
      `PlotFeatures` (joins ID → FeatureType), `PlotResources` (joins ID →
      ResourceType), and lookup tables `TerrainTypes`/`FeatureTypes`/
      `ResourceTypes`. Foreign keys are not declared, but the shared ID
      column makes the join unambiguous. 1144 = 44 * 26, so ID is dense and
      0-indexed.
    action: >
      Build plan with main_table="Plots", key_kind="xy",
      metadata_table="Map", width_column="Width", joins on PlotFeatures
      and PlotResources, lookups on the three *Types tables. Run
      extract_to_json.py with --shape array (downstream adjacency math
      iterates in order).
    outcome: >
      { "metadata": {"Width":44,"Height":26,...},
        "tiles": [{"x":0,"y":0,"TerrainType":"GRASS","FeatureType":null,...}, ...] }

  - need: Inspect an unfamiliar SQLite DB before deciding what to extract.
    context: Schema report shows one dominant table and three small *Types lookups.
    action: Run in `explore-only` mode; surface the report; ask the user which tables matter.
    outcome: Plan authored interactively before any extraction runs.

anti_patterns:
  - Querying tables before introspecting the schema — column names and key shapes are not what you assume.
  - Using INNER JOIN where LEFT JOIN is needed — silently drops main-table rows lacking an auxiliary record. extract_to_json.py uses LEFT-JOIN semantics by default; don't post-process in a way that breaks that.
  - Assuming the linear ID is 0-indexed without checking. Verify with MIN(ID)/MAX(ID)/COUNT(*). If MIN(ID)==1, coordinate math becomes (id-1) % width.
  - Forgetting to pull Width/Height from the metadata/config table before computing (x, y). Never hardcode grid dimensions.
  - Hardcoding table names that vary between map versions or DLCs. Derive every name from sqlite_master in the schema report.
  - Treating .Civ6Map files as binary. They are SQLite — open with sqlite3.connect, not a binary reader.
  - Resolving lookups by JOINing in SQL when the lookup table is missing — the join silently returns zero rows. The lookups field in the plan applies an in-place dict mapping and warns on missing tables instead.
  - Skipping spot-check on multi-join extractions. Silent join-loss is the most common defect; comparing len(items) to the schema report's row_count catches it instantly.
```
