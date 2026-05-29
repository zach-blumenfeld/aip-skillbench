---
name: hex-grid-spatial
description: Hex grid spatial utilities for odd-r offset coordinate systems (Civ6-style). Use when working with hexagonal grids, calculating hex distances, finding hex neighbors, checking adjacency, or running spatial-range queries on hex maps.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Provide correct, deterministic hex-grid math for an "odd-r" horizontal
  offset coordinate system (odd rows shifted right by half a hex) — the
  layout Civ6 uses. Covers neighbor lookup, direction queries, hex
  distance via cube-coordinate conversion, adjacency checks, and
  spatial-range queries. All operations are pure functions over integer
  (x, y) tile coordinates; the agent picks the operation it needs.

trigger_when:
  - Working on a hex-grid map and needing the 6 neighbors of a tile.
  - Computing distance between two hex tiles.
  - Checking whether two tiles are adjacent.
  - Enumerating all tiles within a radius (e.g., a city's workable tiles).
  - Translating between an (x, y) tile and an edge direction (0–5).
  - Any Civ6 / Civ-style adjacency, placement, or spatial-query task.

do_not_use_when:
  - The grid uses square or triangular cells, not hexes.
  - The hex grid uses axial, cube, or even-r offset coordinates rather
    than odd-r. The direction tables baked into the script are odd-r
    specific; using them on a different system will silently return
    wrong neighbors.
  - The task only needs Euclidean pixel distance for rendering; this
    skill returns integer tile distance, not screen distance.

steps:
  - name: get-neighbors
    description: Return all 6 neighboring (x, y) tiles of a hex, respecting the odd-r row offset.
    script: scripts/hex_utils.py
    inputs:
      - name: x
        type: integer
        description: Column of the source tile.
      - name: y
        type: integer
        description: Row of the source tile. Parity (y % 2) selects the direction table.
    outputs:
      - name: neighbors
        type: list[object]
        description: List of six (x, y) tuples, ordered by direction index 0..5 (E, NE, NW, W, SW, SE).
  - name: neighbor-at-direction
    description: Return the single neighbor (x, y) in a given edge direction (0=E, 1=NE, 2=NW, 3=W, 4=SW, 5=SE).
    script: scripts/hex_utils.py
    inputs:
      - name: x
        type: integer
      - name: y
        type: integer
      - name: direction
        type: integer
        description: Edge direction in 0..5.
    outputs:
      - name: neighbor
        type: object
        description: (x, y) tuple of the neighbor in that direction.
  - name: direction-to-neighbor
    description: Return the direction index (0..5) from a source tile to an adjacent target tile, or null when not adjacent.
    script: scripts/hex_utils.py
    inputs:
      - name: x1
        type: integer
      - name: y1
        type: integer
      - name: x2
        type: integer
      - name: y2
        type: integer
    outputs:
      - name: direction
        type: integer
        nullable: true
        description: Edge direction 0..5, or null if (x2, y2) is not one of the 6 neighbors of (x1, y1).
  - name: hex-distance
    description: Integer hex distance between two tiles via odd-r → cube conversion. Do not approximate with Manhattan or Euclidean distance on offset coordinates — both give wrong answers across row-parity boundaries.
    script: scripts/hex_utils.py
    inputs:
      - name: x1
        type: integer
      - name: y1
        type: integer
      - name: x2
        type: integer
      - name: y2
        type: integer
    outputs:
      - name: distance
        type: integer
        description: Number of hex steps between the two tiles.
  - name: is-adjacent
    description: True iff two tiles are exactly one hex apart. Thin wrapper over hex-distance for readability.
    script: scripts/hex_utils.py
    inputs:
      - name: x1
        type: integer
      - name: y1
        type: integer
      - name: x2
        type: integer
      - name: y2
        type: integer
    outputs:
      - name: adjacent
        type: boolean
  - name: tiles-in-range
    description: All tiles within `radius` hexes of a center, excluding the center. Uses hex-distance for the filter, so the result is the correct hex disc — not the bounding-box square.
    script: scripts/hex_utils.py
    inputs:
      - name: x
        type: integer
      - name: y
        type: integer
      - name: radius
        type: integer
        description: Inclusive maximum hex distance.
    outputs:
      - name: tiles
        type: list[object]
        description: List of (x, y) tuples within `radius` of (x, y), excluding the center itself.
  - name: opposite-direction
    description: Return the direction index 180° opposite the given one (e.g., E↔W).
    script: scripts/hex_utils.py
    inputs:
      - name: direction
        type: integer
    outputs:
      - name: opposite
        type: integer

scenarios:
  - need: Find the 6 neighbors of an odd-row tile (21, 13).
    action: Call `get_neighbors(21, 13)` from `scripts/hex_utils.py`.
    outcome: "[(22,13), (22,12), (21,12), (20,13), (21,14), (22,14)] — note (22,12) and (22,14) reflect the odd-row right shift on the NE/SE diagonals."
  - need: Find the 6 neighbors of an even-row tile (21, 14).
    action: Call `get_neighbors(21, 14)`.
    outcome: "[(22,14), (21,13), (20,13), (20,14), (20,15), (21,15)] — even-row diagonals do NOT shift right."
  - need: Distance from (0, 0) to (3, 0).
    action: Call `hex_distance(0, 0, 3, 0)`.
    outcome: "3."
  - need: Check adjacency between (21, 13) and (21, 14).
    action: Call `is_adjacent(21, 13, 21, 14)` (or equivalently `hex_distance(...) == 1`).
    outcome: True (the two tiles share an edge across the row boundary).
  - need: Enumerate every workable tile within range 3 of a city centered at (21, 13).
    action: Call `get_tiles_in_range(21, 13, 3)`.
    outcome: 36 tiles — the full hex disc of radius 3 minus the center.
  - need: Determine the edge direction from (5, 5) to its eastern neighbor (6, 5).
    action: Call `get_direction_to_neighbor(5, 5, 6, 5)`.
    outcome: 0 (East).

anti_patterns:
  - Using Manhattan distance |x1-x2| + |y1-y2| or Euclidean distance on offset coordinates. Both miscount across row-parity boundaries; always go through `hex_distance` (cube conversion).
  - Sharing one direction-offset table for all rows. Odd and even rows have different NE/NW/SW/SE offsets; only E (0) and W (3) are row-invariant. The script branches on `y % 2` — do not strip that branch.
  - Iterating a bounding box and treating it as "tiles in range". A square bounding box of side `2*radius+1` includes corner tiles whose hex distance exceeds `radius`; filter with `hex_distance` (which `get_tiles_in_range` already does).
  - Re-deriving direction offsets from a hex picture or from cube math on the fly. The constants in `DIRECTIONS_EVEN_ROW` / `DIRECTIONS_ODD_ROW` are the canonical odd-r tables — use them.
  - Assuming odd-q (odd-column) offset. This skill is odd-r (odd-row). If the target grid is odd-q or even-r, the offset tables are wrong; do not use this skill — see do_not_use_when.
  - "Treating direction indices as arbitrary. The mapping is fixed: 0=E, 1=NE, 2=NW, 3=W, 4=SW, 5=SE, and `opposite_direction(d) == (d + 3) % 6` depends on that ordering."
```
