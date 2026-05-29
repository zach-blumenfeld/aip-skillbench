---
name: sqlite-map-parser
description: Parse SQLite databases into structured JSON data. Use when exploring unknown database schemas, understanding table relationships, and extracting map data as JSON.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Reverse-engineer an unknown SQLite database into a clean, structured
  JSON document. Walks the agent from blind schema introspection through
  relationship inference, planned extraction, and an output shape that
  matches how downstream code wants to read the data. Built for map and
  grid databases (e.g. Civilization 6 .Civ6Map files) but applies to any
  SQLite source where the schema must be discovered before data can be
  extracted.

trigger_when:
  - Handed a .sqlite, .db, or .Civ6Map file with no documented schema.
  - Need to convert table-shaped data into JSON the rest of a pipeline consumes.
  - Working with grid/map data where tiles, terrain, features, and resources are split across joined tables.
  - User asks "what's in this database?" or "extract the map as JSON".

do_not_use_when:
  - The schema is already documented and only a single targeted query is needed.
  - The source isn't SQLite (Postgres, MySQL, CSV, Parquet — wrong tool).

steps:
  - name: explore-schema
    description: Deterministic schema dump — every table's columns, primary key, foreign keys, indexes, row count, and a few sample rows. Always the first step; the dump is the source of truth for everything that follows.
    script: scripts/explore_schema.py
    inputs:
      - name: db_path
        type: string
        description: Path to the SQLite database file.
    outputs:
      - name: schema_dump
        type: object
        description: "{ db_path, tables: { <name>: { columns, primary_key, foreign_keys, indexes, row_count, sample_rows } } }."

  - name: identify-key-tables
    description: >
      Read schema_dump and label each table by role. Look for a single-row
      metadata/config table (width, height, seed, settings), one main entity
      table (one row per tile / record / unit), overlay tables that share
      the main key and add columns, and lookup tables that map codes to
      labels. When a table doesn't fit any role, mark it `unknown` rather
      than forcing a guess.
    inputs:
      - name: schema_dump
        type: object
    outputs:
      - name: table_roles
        type: object
        description: Map of table_name → { role ∈ [metadata, main, overlay, lookup, unknown], rationale }.

  - name: plan-extraction
    description: >
      Decide the output shape from table_roles. Pick the join key on the
      main table — an explicit ID column, a composite (X, Y), or a linear
      index decomposed as `x = id % width, y = id // width`. Choose a dict
      output when downstream code does keyed lookups (`tiles["3,4"]`), an
      array when order matters or keys are dense integers. List which
      overlays and lookups merge in and under what field names. See
      `references/common-patterns.md` for the grid / hierarchical / lookup
      archetypes.
    inputs:
      - name: schema_dump
        type: object
      - name: table_roles
        type: object
    outputs:
      - name: extraction_plan
        type: object
        description: "{ main_table, join_key, output_shape, overlays: [{table, join_on, field_name}], lookups: [{table, code_col, label_col, target_field}] }."
    one_of:
      - dict output (natural unique keys like coordinates)
      - array output (ordered or dense-integer-keyed)

  - name: extract-and-transform
    description: >
      Implement extraction_plan in Python following the template in
      `references/extraction-patterns.md`. Open with `sqlite3.Row` as the
      row factory so columns are addressable by name. Pull the metadata
      row first, build an index from the main table, then merge each
      overlay with LEFT-JOIN semantics (a missing overlay row leaves the
      field at its default, it doesn't drop the parent). Wrap any optional
      table read in the `safe_query` helper so a schema variant without
      that overlay degrades gracefully instead of raising.
    inputs:
      - name: db_path
        type: string
      - name: extraction_plan
        type: object
    outputs:
      - name: structured_output
        type: object
        description: "{ metadata: {...}, <items_key>: dict|list } — the parsed JSON document."

  - name: validate-output
    description: >
      Sanity-check structured_output before handing it on. (1) Item count
      matches the main table's row_count from schema_dump. (2) For grid
      sources with width/height in metadata, `len(items) == width * height`.
      (3) Spot-check 3–5 items against `schema_dump.sample_rows` and
      confirm overlay/lookup fields line up. (4) Confirm every overlay
      field that should ever be populated is present on at least one item
      — if it's always null, the join key is wrong.
    inputs:
      - name: structured_output
        type: object
      - name: schema_dump
        type: object
    outputs:
      - name: validated_output
        type: object

scenarios:
  - need: Parse a .Civ6Map file into JSON keyed by (x, y) so a placement optimizer can read tile terrain.
    context: >
      explore-schema surfaces a single-row `Map` table with `Width`,
      `Height`, `MapSeed`; a `Plots` table whose `ID` is a linear index
      0..Width*Height-1 with `TerrainType` and `Elevation` columns; and
      `PlotFeatures` / `PlotResources` joining on `PlotID`.
    action: >
      Roles → Map=metadata, Plots=main, PlotFeatures+PlotResources=overlay.
      Plan → main_table=Plots, join_key=(ID % Width, ID // Width),
      output_shape=dict, overlays merged as `feature` and `resource`.
      Extract produces `{"metadata": {"width": 44, "height": 26}, "tiles": {"0,0": {...}, ...}}`.
    outcome: Downstream skills index tiles by coordinate without re-querying the DB.

  - need: Inspect a database whose tables and column names are entirely unknown.
    context: explore-schema is the deliverable on its own. No extraction needed; the user just wants to know what's in the file.
    action: Run explore-schema, then present the roles inferred by identify-key-tables as a one-page summary.
    outcome: User gets a schema map without opening a SQL REPL.

anti_patterns:
  - Writing extraction code before running explore-schema. The schema dump is the source of truth, not your guess about it.
  - Assuming the main table has an obvious `id` column. Spatial sources often pack (x, y) into a single linear `ID` that must be decomposed.
  - Picking an array output when downstream code wants O(1) lookups, or a dict output when order matters and items have dense integer keys.
  - INNER-joining overlay tables. Use LEFT-JOIN semantics (or per-row `safe_query`) so parents without overlays still appear in the output.
  - Hard-coding queries against tables that may not exist across schema variants. Wrap optional reads in `safe_query` so a missing overlay returns [] instead of crashing.
```
