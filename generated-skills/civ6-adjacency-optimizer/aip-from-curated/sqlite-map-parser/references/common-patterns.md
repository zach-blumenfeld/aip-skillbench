# Common SQLite Schema Patterns

Load this reference when the schema report from `explore_schema.py` is in
hand and you need to pick an extraction shape. Each pattern lists the
signal in the schema, the join strategy, and the `extract_to_json.py` plan
fragment that handles it.

## 1. Grid / map data (Civ6Map and similar)

**Signal in schema report:**
- A single-row metadata/config table with `Width` and `Height` columns.
- A large main table (rows ≈ `Width * Height`) with `ID` as a dense linear
  index (often 0..N-1).
- One or more auxiliary tables that share the same `ID` column (terrain
  features, resources, rivers, improvements). Foreign keys may or may not
  be declared.

**Coordinate math:**
```
x = id % width
y = id // width
```
Always pull `width` from the metadata table; never hardcode. Verify with
`MIN(ID)`, `MAX(ID)`, and `COUNT(*)` — if `MIN(ID) == 1` the index is
1-based and the math becomes `(id - 1) % width`.

**Plan fragment:**
```json
{
  "main_table": "Plots",
  "id_column":  "ID",
  "key_kind":   "xy",
  "metadata_table": "Map",
  "width_column":  "Width",
  "height_column": "Height",
  "container_key": "tiles",
  "joins": [
    {"table": "PlotFeatures",     "on": "ID", "fields": ["FeatureType"]},
    {"table": "PlotResources",    "on": "ID", "fields": ["ResourceType"]},
    {"table": "PlotImprovements", "on": "ID", "fields": ["ImprovementType"]}
  ]
}
```

## 2. Hierarchical / parent-child

**Signal:**
- Parent table with a primary key.
- Child tables with a foreign key to the parent. `PRAGMA foreign_key_list`
  shows the relationship even when constraints aren't enforced at runtime.

**Strategy:**
- Use LEFT JOIN semantics (the default in `extract_to_json.py`) so parents
  with no children are preserved.
- Group children under the parent by emitting a `list[*]` field per
  parent — this requires a wrapper around `extract_to_json.py`, or a
  post-processing step.

## 3. Enum / lookup tables

**Signal:**
- Small (< few hundred rows) table named `*Types`, `*Codes`, `*Kinds`.
- Two columns: an integer/string `Type`/`Code` key and a human-readable
  `Name`/`Description` value.

**Strategy:**
Use the `lookups` field in the extraction plan. Resolve in-place so the
output contains the human-readable string, not the code.

**Plan fragment:**
```json
{
  "lookups": [
    {"table": "FeatureTypes",  "key": "Type", "value": "Name", "for_field": "FeatureType"},
    {"table": "TerrainTypes",  "key": "Type", "value": "Name", "for_field": "TerrainType"},
    {"table": "ResourceTypes", "key": "Type", "value": "Name", "for_field": "ResourceType"}
  ]
}
```

## 4. Sparse overlays

**Signal:**
- An auxiliary table whose row count is << the main table's row count
  (e.g., only river-bearing tiles, only resource tiles).

**Strategy:**
- Join as usual — `extract_to_json.py` LEFT-JOINs and leaves the field
  unset on rows that don't appear in the overlay.
- After extraction, treat missing fields as the default ("no feature").

## Output shape decision

- **Array** — when downstream code iterates in order (adjacency math,
  rendering by index, sequential indexing into the grid). This is the
  default and matches `--shape array`.
- **Map (keyed by `"x,y"` or natural ID)** — when downstream code does
  random-access lookups (e.g., "what's at (3, 7)?") and the natural key
  is unique. Use `--shape map`.

When in doubt, emit an array — the agent or downstream consumer can build
a lookup dict in one line.
