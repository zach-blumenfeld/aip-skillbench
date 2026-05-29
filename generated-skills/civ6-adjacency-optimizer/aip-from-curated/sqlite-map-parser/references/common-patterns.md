# Common Schema Patterns & Debugging SQL

Reference for the `identify-key-tables` and `plan-extraction` steps when
the schema dump alone isn't enough to pin down a table's role.

## Pattern: Grid / Map data

- One **metadata** table with a single row carrying `Width`, `Height`,
  and assorted seed/config columns.
- A **main** tile table with one row per cell. Primary key is either
  `(X, Y)` or a single linear index (`ID = Y * Width + X`).
- **Overlay** tables (features, resources, improvements) joining onto
  the tile primary key. Always sparse — most tiles have no overlay.

Decompose a linear ID once at read time:

```python
x = id_ % width
y = id_ // width
```

## Pattern: Hierarchical / Parent-child

- A **parent** table with a primary key.
- One or more **child** tables with a foreign key back to the parent.
- Use `LEFT JOIN` semantics when building the structured output —
  parents without children should still appear, just with empty
  child collections.

## Pattern: Enum / Lookup

- A small **lookup** table mapping a code (`TYPE_GRASS`) to a label
  (`"Grassland"`) or numeric value.
- Resolve at extraction time so the structured JSON carries the
  human-readable label, not the opaque code. Keep the original code in
  a separate field only when downstream code needs to round-trip it.

## Debugging SQL

When `schema_dump` doesn't answer a question, drop into the SQLite REPL
with these one-liners:

```sql
-- Sample data from any table
SELECT * FROM TableName LIMIT 5;

-- Row count
SELECT COUNT(*) FROM TableName;

-- Distinct values in a column (good for enum discovery)
SELECT DISTINCT ColumnName FROM TableName;

-- Null-check a candidate join key
SELECT COUNT(*) FROM TableName WHERE ColumnName IS NULL;

-- Confirm a join works on real data
SELECT m.*, r.ExtraData
FROM MainTable m
LEFT JOIN RelatedTable r ON m.ID = r.ID
LIMIT 10;
```

The schema-introspection PRAGMAs `explore_schema.py` already runs, kept
here as a reference for the agent when it wants to issue them directly:

```sql
SELECT name FROM sqlite_master WHERE type='table';
PRAGMA table_info(TableName);
SELECT sql FROM sqlite_master WHERE name='TableName';
PRAGMA index_list(TableName);
PRAGMA index_info(index_name);
PRAGMA foreign_key_list(TableName);
```
