# .Civ6Map File Format

`.Civ6Map` files shipped by Modbuddy / Steam Workshop are **SQLite
databases**. Open them with the `sqlite3` module:

```python
import sqlite3
conn = sqlite3.connect(map_path)
conn.row_factory = sqlite3.Row
```

If `sqlite3.connect` raises "file is not a database", the file may be a
binary save format. In that case, dump the first 16 bytes — Civ6 SQLite
files start with `SQLite format 3\x00`. If they start with `CIV6MAP` or
similar, fall back to the binary parser (see bottom of this file).

## Inspecting structure (do this first)

```python
cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
print([r[0] for r in cur])
```

Typical tables (names vary by Civ6 version):

- `Map`               — single row with `Width`, `Height`, `TopLatitude`, `BottomLatitude`, `WrapX`, `WrapY`.
- `Plots`             — one row per tile. Columns include `ID`, `X`, `Y`, `TerrainType`, `FeatureType`, `ResourceType`, `IsImpassable`, `IsCoastal`, `Elevation`, sometimes `Continent`, `RiverEW` / `RiverSE` / `RiverSW` bitmask flags.
- `StartPositions`    — pre-placed civilization start tiles.
- `MapFeatures`       — natural wonders & other multi-tile features.
- `Improvements`      — usually empty for unedited maps.
- `Resources`         — usually empty (resources are in `Plots.ResourceType`).
- `Rivers`            — edge-level river data on some versions.
- `CliffEdges`        — cliff/escarpment edges.

Always run `PRAGMA table_info(<tablename>)` on each table before relying
on column names. Some columns are nullable; missing river data on
`Plots` means rivers live in the `Rivers` table.

## Terrain & feature enum values

`TerrainType` and `FeatureType` are string constants in Civ6:

- Terrain: `TERRAIN_GRASS`, `TERRAIN_GRASS_HILLS`, `TERRAIN_GRASS_MOUNTAIN`,
  `TERRAIN_PLAINS`, `TERRAIN_PLAINS_HILLS`, `TERRAIN_PLAINS_MOUNTAIN`,
  `TERRAIN_DESERT`, `TERRAIN_DESERT_HILLS`, `TERRAIN_DESERT_MOUNTAIN`,
  `TERRAIN_TUNDRA`, `TERRAIN_TUNDRA_HILLS`, `TERRAIN_TUNDRA_MOUNTAIN`,
  `TERRAIN_SNOW`, `TERRAIN_SNOW_HILLS`, `TERRAIN_SNOW_MOUNTAIN`,
  `TERRAIN_COAST`, `TERRAIN_OCEAN`.
- Feature: `FEATURE_FOREST` (= Woods), `FEATURE_JUNGLE` (= Rainforest),
  `FEATURE_MARSH`, `FEATURE_FLOODPLAINS`, `FEATURE_OASIS`, `FEATURE_ICE`,
  `FEATURE_REEF`, `FEATURE_LAKE`. Natural wonders use `FEATURE_*` names
  (e.g., `FEATURE_GALAPAGOS`, `FEATURE_GEOTHERMAL_FISSURE`).

Mountains are detected via `TerrainType.endswith("_MOUNTAIN")`. Hills via
`_HILLS`. Water via `TERRAIN_COAST` / `TERRAIN_OCEAN`. Coast (shallow
water adjacent to land) is `TERRAIN_COAST`; Harbors need this terrain.

## Rivers

Two common encodings:

1. **On Plots**: columns `RiverEast`, `RiverSouthEast`, `RiverSouthWest`
   (integers; nonzero = river on that hex edge). A tile is
   "adjacent to a river" if any of these three edges OR the matching
   edges of its neighbors are set.
2. **In Rivers table**: edge rows with `Plot_ID`, `EdgeDirection`. Build
   an edge index keyed on `(x, y, edge)`.

For Commercial Hub adjacency, the canonical test is: the district tile
shares at least one hex edge with a river segment.

## Worked extraction

```python
def load_map(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    m = conn.execute("SELECT * FROM Map LIMIT 1").fetchone()
    width, height = m["Width"], m["Height"]
    grid = {}
    for r in conn.execute("SELECT * FROM Plots"):
        grid[(r["X"], r["Y"])] = dict(r)
    return width, height, grid
```

Always read every column. The parser script in `scripts/parse_map.py`
does this defensively (skips missing columns, uses `dict(row)`).

## Binary fallback (rare)

Modern Civ6 ships SQLite maps. If you encounter a true binary format
(`magic == b"CIV6MAP"` etc.), the layout is undocumented; in that case
report the file header to the user and stop — guessing the binary layout
risks an invalid placement. Prefer to read any `scenario.json` companion
fields (some scenarios pre-extract terrain into JSON).

## Scenario.json

Open and inspect first. Likely fields:

```json
{
  "map_file": "/data/scenario_3/map.Civ6Map",
  "num_cities": 1,
  "population": 6,
  "civilization": "CIVILIZATION_GREECE"
}
```

`civilization` may carry a `CIVILIZATION_` prefix or a friendly name —
strip the prefix when comparing.
