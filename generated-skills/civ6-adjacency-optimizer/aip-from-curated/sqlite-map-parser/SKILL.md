---
name: sqlite-map-parser
description: Parse SQLite databases into structured JSON data. Use when exploring unknown database schemas, understanding table relationships, and extracting map data as JSON.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Parse SQLite databases into structured JSON by exploring the schema first,
  then mapping table relationships, then extracting and shaping the data.
  Targeted at unknown databases where the schema must be discovered before any
  extraction is safe — especially grid/map data and other spatially-indexed
  records.

trigger_when:
  - Exploring an unknown SQLite database schema.
  - Understanding table relationships (primary keys, foreign keys, joins) in SQLite.
  - Extracting map, grid, or spatial data from SQLite as structured JSON.
  - User mentions a `.db` / `.sqlite` file and asks for JSON output.

steps:
  - name: explore-schema
    description: |
      Always start by understanding what tables exist and their structure.

      List all tables:
      ```sql
      SELECT name FROM sqlite_master WHERE type='table';
      ```

      Inspect a table's columns and types:
      ```sql
      PRAGMA table_info(TableName);
      SELECT sql FROM sqlite_master WHERE name='TableName';
      ```

      Find primary and unique keys:
      ```sql
      PRAGMA table_info(TableName);   -- 'pk' column shows primary key order
      PRAGMA index_list(TableName);   -- all indexes (includes unique constraints)
      PRAGMA index_info(index_name);  -- columns in an index
      ```
  - name: understand-relationships
    description: |
      Identify foreign keys and the join patterns that connect tables.

      Foreign keys:
      ```sql
      PRAGMA foreign_key_list(TableName);
      ```

      ID-based joins — tables often share an ID column where the main table
      holds the primary key and related tables reference it:
      ```sql
      SELECT m.*, r.ExtraData
      FROM MainTable m
      LEFT JOIN RelatedTable r ON m.ID = r.ID;
      ```

      Coordinate-based keys — spatial data often encodes (x, y) as a linear
      index into a grid:
      ```python
      # If ID represents a linear index into a grid:
      x = id % width
      y = id // width
      ```
  - name: extract-transform
    description: |
      Connect with `sqlite3.Row` so columns are accessible by name, then build
      an indexed data structure and join in related rows.

      Basic pattern:
      ```python
      import sqlite3
      import json

      def parse_sqlite_to_json(db_path):
          conn = sqlite3.connect(db_path)
          conn.row_factory = sqlite3.Row  # Access columns by name
          cursor = conn.cursor()

          # 1. Explore schema
          cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
          tables = [row[0] for row in cursor.fetchall()]

          # 2. Get dimensions/metadata from config table
          cursor.execute("SELECT * FROM MetadataTable LIMIT 1")
          metadata = dict(cursor.fetchone())

          # 3. Build indexed data structure
          data = {}
          cursor.execute("SELECT * FROM MainTable")
          for row in cursor.fetchall():
              key = row["ID"]  # or compute: (row["X"], row["Y"])
              data[key] = dict(row)

          # 4. Join related data
          cursor.execute("SELECT * FROM RelatedTable")
          for row in cursor.fetchall():
              key = row["ID"]
              if key in data:
                  data[key]["extra_field"] = row["Value"]

          conn.close()
          return {"metadata": metadata, "items": list(data.values())}
      ```

      Handle missing tables gracefully — not every database has every table:
      ```python
      def safe_query(cursor, query):
          try:
              cursor.execute(query)
              return cursor.fetchall()
          except sqlite3.OperationalError:
              return []  # Table doesn't exist
      ```
  - name: output-json
    description: |
      Choose the output shape based on whether keys are meaningful or order matters.

      Map/dictionary output — use when items have natural unique keys
      (e.g., coordinate strings):
      ```json
      {
        "metadata": {"width": 44, "height": 26},
        "tiles": {
          "0,0": {"terrain": "GRASS", "feature": null},
          "1,0": {"terrain": "PLAINS", "feature": "FOREST"},
          "2,0": {"terrain": "COAST", "resource": "FISH"}
        }
      }
      ```

      Array output — use when order matters or keys are simple integers:
      ```json
      {
        "metadata": {"width": 44, "height": 26},
        "tiles": [
          {"x": 0, "y": 0, "terrain": "GRASS"},
          {"x": 1, "y": 0, "terrain": "PLAINS", "feature": "FOREST"},
          {"x": 2, "y": 0, "terrain": "COAST", "resource": "FISH"}
        ]
      }
      ```

decisions:
  - signal: Items have natural unique keys (e.g., coordinate strings, named IDs).
    action: Emit map/dictionary output keyed by those identifiers.
  - signal: Order matters, or keys are simple sequential integers.
    action: Emit array output with explicit coordinate or index fields on each item.
  - signal: A query may reference a table that does not exist in this database.
    action: Wrap the call in `try/except sqlite3.OperationalError` and return `[]` on failure (see `safe_query`).
  - signal: ID is a linear index into a grid and (x, y) are needed.
    action: Compute `x = id % width`, `y = id // width` using width pulled from the metadata table.

scenarios:
  - need: Grid or map data with base positions plus optional overlays (features, resources).
    context: Main table holds positions and base properties; feature tables join on the position ID.
    action: Extract the main table into a dict keyed by position ID, then LEFT JOIN feature tables and attach extra fields. Compute (x, y) from the linear ID when needed.
    outcome: A single structured JSON object with metadata plus per-position records that include base and overlay fields.
  - need: Hierarchical parent/child data.
    context: Parent table has the primary key; child tables reference it via foreign key.
    action: Use `LEFT JOIN` from parent to child so all parents are preserved even when no children match.
    outcome: Nested or flattened JSON that retains parent rows without children.
  - need: Enum or lookup tables mapping codes to human-readable descriptions.
    context: Type tables map opaque codes (e.g., `TERRAIN_GRASS`) to readable values.
    action: JOIN the lookup table during extraction so output carries the readable values rather than raw codes.
    outcome: JSON consumers see meaningful labels without needing the lookup table.

search_shortcuts:
  - category: Debugging queries
    body: |
      Sample data from any table:
      ```sql
      SELECT * FROM TableName LIMIT 5;
      ```

      Count rows:
      ```sql
      SELECT COUNT(*) FROM TableName;
      ```

      Find distinct values in a column:
      ```sql
      SELECT DISTINCT ColumnName FROM TableName;
      ```

      Check for nulls:
      ```sql
      SELECT COUNT(*) FROM TableName WHERE ColumnName IS NULL;
      ```

anti_patterns:
  - Extracting data before inspecting the schema — column names and types must be discovered first.
  - Assuming every expected table exists; unguarded queries raise `sqlite3.OperationalError`.
  - Accessing columns by positional index instead of using `sqlite3.Row` for name-based access.
  - Hard-coding grid dimensions instead of reading them from the metadata table.
```
