---
name: hex-grid-spatial
description: Hex grid spatial utilities for offset coordinate systems. Use when working with hexagonal grids, calculating distances, finding neighbors, or spatial queries on hex maps.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Hex-grid spatial math for odd-r offset coordinates (odd rows shifted right
  by half a hex). Tile 0 is bottom-left; x increases rightward (columns); y
  increases upward (rows). Edge directions are indexed 0=East, 1=NE, 2=NW,
  3=West, 4=SW, 5=SE. Use this skill instead of re-deriving neighbor offsets
  or distance formulas — the row-parity rules for diagonals are easy to get
  wrong by hand.

trigger_when:
  - Working with hexagonal grids in odd-r offset coordinates.
  - Finding the neighbors of a hex, or the neighbor in a specific direction.
  - Computing the distance between two hex tiles.
  - Enumerating all tiles within a given radius of a center tile (e.g., a
    city's workable tiles).
  - Checking whether two hexes are adjacent.
  - Converting between an offset coordinate pair and a direction index.

do_not_use_when:
  - The grid is square or uses axial/cube coordinates directly — the offset
    conversions here assume odd-r.
  - The grid uses "odd-q" (odd-column) or "even-r"/"even-q" offsets. Direction
    offsets differ; do not reuse these helpers without adapting them.

steps:
  - name: import-helpers
    description: >
      Import the helpers from `scripts/hex_utils.py` rather than re-implementing
      neighbor offsets or cube-coordinate conversion. Available functions:
      `get_neighbors`, `get_neighbor_at_direction`, `get_direction_to_neighbor`,
      `hex_distance`, `is_adjacent`, `get_tiles_in_range`,
      `get_opposite_direction`.
  - name: select-helper
    description: >
      Pick the helper that matches the query. Use the `decisions` table below to
      map a need ("I want all neighbors", "I want distance", "I want tiles
      within radius N") to the right function.
  - name: account-for-row-parity
    description: >
      Diagonal directions (NE/NW/SW/SE — indices 1, 2, 4, 5) differ between even
      and odd rows. East (0) and West (3) are always (+1, 0) and (-1, 0). The
      helpers handle parity internally; only worry about parity if you bypass
      them and write offsets by hand. See `anti_patterns`.
  - name: verify-with-distance
    description: >
      When in doubt about adjacency or range, call `hex_distance` or
      `is_adjacent` rather than comparing coordinate deltas directly. The cube
      conversion handles the odd-row shift correctly; raw delta comparisons do
      not.

decisions:
  - signal: Need all 6 neighbors of a tile.
    action: Call `get_neighbors(x, y)` — returns a list of 6 (x, y) tuples.
  - signal: Need the neighbor in a specific edge direction (0–5).
    action: Call `get_neighbor_at_direction(x, y, direction)`.
  - signal: Have two adjacent tiles and need the direction from one to the other.
    action: >
      Call `get_direction_to_neighbor(x1, y1, x2, y2)`. Returns 0–5, or `None`
      if the tiles are not adjacent.
  - signal: Need the integer hex distance between two tiles.
    action: Call `hex_distance(x1, y1, x2, y2)`.
  - signal: Need a boolean adjacency check.
    action: >
      Call `is_adjacent(x1, y1, x2, y2)` (equivalent to
      `hex_distance(...) == 1`).
  - signal: Need every tile within radius N of a center (e.g., city workable tiles).
    action: >
      Call `get_tiles_in_range(x, y, radius)`. Excludes the center tile.
      Yields 6 tiles for radius 1, 18 for radius 2, etc.
  - signal: Need the direction 180° opposite a given direction.
    action: Call `get_opposite_direction(direction)` — `(direction + 3) % 6`.

scenarios:
  - need: Find the 6 neighbors of tile (21, 13) on an odd row.
    action: >
      `get_neighbors(21, 13)` →
      `[(22,13), (22,12), (21,12), (20,13), (21,14), (22,14)]`.
    outcome: Direction-indexed list of neighbors, with odd-row diagonals applied.
  - need: Compute the distance between (21, 13) and (24, 13).
    action: "`hex_distance(21, 13, 24, 13)` → 3."
    outcome: Integer tile distance via cube-coordinate conversion.
  - need: Check whether (21, 13) and (21, 14) are adjacent.
    action: "`hex_distance(21, 13, 21, 14) == 1` → True (or `is_adjacent(...)`)."
    outcome: Boolean adjacency without hand-rolling row-parity logic.
  - need: Enumerate all tiles a city at (21, 13) could work within radius 3.
    action: "`get_tiles_in_range(21, 13, 3)` → list of 36 tiles (excludes center)."
    outcome: Workable-tile set ready to iterate for adjacency or yield calculations.

anti_patterns:
  - >
    Using the same diagonal offsets for even and odd rows. NE, NW, SW, SE
    shift between (0,±1)/(-1,±1) on even rows and (1,±1)/(0,±1) on odd rows.
    Always branch on `y % 2` or call the bundled helpers.
  - >
    Computing distance from raw `|x1-x2| + |y1-y2|` or Chebyshev deltas. That
    only works on square grids; on odd-r hexes you must convert to cube
    coordinates first (which `hex_distance` does).
  - >
    Reimplementing neighbor or distance logic inline instead of importing
    from `scripts/hex_utils.py`. The helpers are stateless and unit-testable;
    duplicating them invites row-parity bugs.
  - >
    Including the center tile in "tiles in range" results. `get_tiles_in_range`
    explicitly excludes the center; downstream callers expecting the center
    must add it back.
```
