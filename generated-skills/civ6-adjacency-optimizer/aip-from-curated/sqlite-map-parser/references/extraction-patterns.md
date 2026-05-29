# Extraction Patterns

Code templates the `extract-and-transform` step adapts. Pulled from the
canonical sqlite-map-parser SKILL.md so they live next to the YAML body
rather than inline in it.

## Base parser

The default shape: one metadata row at the top, an indexed main table,
overlay tables merged in by ID.

```python
import sqlite3
import json

def parse_sqlite_to_json(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # column access by name
    cursor = conn.cursor()

    # 1. Metadata row (width, height, settings, ...)
    cursor.execute("SELECT * FROM MetadataTable LIMIT 1")
    metadata = dict(cursor.fetchone())

    # 2. Index the main table by its primary key
    data = {}
    cursor.execute("SELECT * FROM MainTable")
    for row in cursor.fetchall():
        key = row["ID"]                       # or (row["X"], row["Y"])
        data[key] = dict(row)

    # 3. Merge overlay tables (LEFT-JOIN semantics)
    cursor.execute("SELECT * FROM RelatedTable")
    for row in cursor.fetchall():
        key = row["ID"]
        if key in data:
            data[key]["extra_field"] = row["Value"]

    conn.close()
    return {"metadata": metadata, "items": list(data.values())}
```

## Missing-table-safe helper

Some databases ship without overlay tables that other variants have. Wrap
each optional query so a missing table returns `[]` rather than aborting
the parser.

```python
def safe_query(cursor, query, params=()):
    try:
        cursor.execute(query, params)
        return cursor.fetchall()
    except sqlite3.OperationalError:
        return []  # table or column doesn't exist
```

## Linear-index → (x, y)

When the main table's primary key is a single integer indexing into a
grid, decompose it once at read time so downstream code never has to.

```python
width = metadata["Width"]
# `id` is a 0..width*height-1 linear index
x = id_ % width
y = id_ // width
```

Order matters: row-major (`y = id // width`) is the SQLite/Civ6
convention. Column-major produces correct counts but wrong neighbors.

## Output shapes

### Dict keyed by natural ID

Use when items have natural unique keys and downstream code does O(1)
lookups by key (`tiles["12,4"]`).

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

### Array preserving order

Use when item order is meaningful or keys are dense integers — iterating
is more natural than keying.

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
