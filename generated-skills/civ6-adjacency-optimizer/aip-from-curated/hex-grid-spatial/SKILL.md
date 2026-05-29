---
name: hex-grid-spatial
description: Hex grid spatial utilities for Civ6's odd-r offset coordinate system. Use when computing neighbors, hex distance, range queries, adjacency checks, or direction math on hexagonal maps — e.g., evaluating district adjacency bonuses, enumerating workable city tiles, or any spatial query where odd-row offset must be handled correctly.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Hex grid spatial primitives for Civ6's odd-r horizontal offset coordinate
  system (odd rows shifted right by half a hex; x increases rightward, y
  increases upward, tile 0 at bottom-left). Provides scripted functions for
  neighbor lookup, hex distance, range queries, adjacency tests, and
  direction math. These are the geometry building blocks needed to compute
  district adjacency bonuses, enumerate city workable tiles, and run any
  spatial query on the Civ6 map. All conditional logic (even-row vs odd-row
  offset, cube-coordinate conversion) lives in scripts/hex_utils.py — call
  the functions, don't re-derive the math inline.

trigger_when:
  - Need the 6 neighboring tiles of a hex coordinate.
  - Computing distance between two hex coordinates (e.g., is this tile within city working range).
  - Enumerating all tiles within radius N of a center (e.g., workable tiles, area-of-effect queries).
  - Checking whether two hex tiles are adjacent.
  - Translating a (dx, dy) step into a direction index 0–5, or vice versa.
  - Computing adjacency bonuses for a Civ6 district, where adjacency means hex distance 1.
  - Any spatial query on a Civ6 map grid where odd-row offset must be handled correctly.

do_not_use_when:
  - Working with square grids or pointy-top hex grids — this skill is flat-top odd-r only.
  - Pathfinding that requires terrain movement cost — these are pure-geometry utilities.
  - Coordinate systems other than odd-r (e.g., even-r, axial, cube) without first converting.

scope_and_approval: >
  Read-only utility functions. No filesystem, network, or game-state mutation.
  Safe to call freely without approval.

steps:
  - name: load-hex-utils
    description: >
      Import the helpers from scripts/hex_utils.py before any spatial query.
      The module is the source of truth for direction tables, cube-coord
      conversion, and even/odd row handling — read it once if the coordinate
      conventions are unfamiliar.
    script: scripts/hex_utils.py
    outputs:
      - name: hex-utils-module
        type: object
        description: Module exposing get_neighbors, get_neighbor_at_direction, get_direction_to_neighbor, hex_distance, is_adjacent, get_tiles_in_range, get_opposite_direction, and the DIRECTIONS_EVEN_ROW / DIRECTIONS_ODD_ROW lookup tables.

  - name: spatial-query
    description: >
      Pick the function that matches the query and call it. Each option is
      backed by scripts/hex_utils.py — do not reimplement hex math inline.
      Direction indices are 0=E, 1=NE, 2=NW, 3=W, 4=SW, 5=SE.
    depends_on: [load-hex-utils]
    script: scripts/hex_utils.py
    one_of:
      - "get_neighbors(x, y) → list of all 6 neighbor (x, y) tuples; handles even/odd row offset automatically."
      - "get_neighbor_at_direction(x, y, direction) → (x, y) of the neighbor in direction 0–5."
      - "get_direction_to_neighbor(x1, y1, x2, y2) → direction index 0–5 from source to an adjacent target, or None if not adjacent."
      - "hex_distance(x1, y1, x2, y2) → integer hex distance via cube-coordinate conversion."
      - "is_adjacent(x1, y1, x2, y2) → True iff hex_distance == 1."
      - "get_tiles_in_range(x, y, radius) → list of all (x, y) within radius (center excluded)."
      - "get_opposite_direction(direction) → (direction + 3) % 6."
    inputs:
      - name: hex-utils-module
        type: object
      - name: coordinates
        type: object
        description: The (x, y) coordinate(s), direction index, or radius the chosen function needs.
    outputs:
      - name: query-result
        type: object
        description: Function return — list of coordinates, int distance, bool adjacency, or direction index.

scenarios:
  - need: Find the six neighbors of a tile at (21, 13).
    context: y=13 is odd, so the odd-row direction table applies (NE and SE shifted right).
    action: "neighbors = get_neighbors(21, 13)"
    outcome: "[(22, 13), (22, 12), (21, 12), (20, 13), (21, 14), (22, 14)]"

  - need: Distance between (21, 13) and (24, 13).
    action: "dist = hex_distance(21, 13, 24, 13)"
    outcome: "3"

  - need: Confirm (21, 14) is adjacent to (21, 13) for a district adjacency bonus.
    action: "is_adj = is_adjacent(21, 13, 21, 14)"
    outcome: "True — the bonus applies."

  - need: Enumerate every tile a city at (21, 13) can work (radius 3).
    action: "workable = get_tiles_in_range(21, 13, 3)"
    outcome: "Every (x, y) within hex distance 3 of (21, 13), excluding the center."

  - need: Score adjacency for a candidate district placement against several feature tiles.
    context: Civ6 adjacency bonuses depend on which neighbor categories sit on tiles at hex distance 1.
    action: "For each (fx, fy) in feature_tiles: if is_adjacent(dx, dy, fx, fy): add the feature's bonus to the running score."
    outcome: Total adjacency score for the candidate placement.

anti_patterns:
  - Re-deriving neighbor offsets inline. Odd-row vs even-row offsets are asymmetric (NE, NW, SW, SE differ); call get_neighbors instead of hand-rolling deltas.
  - Computing distance with Euclidean or Manhattan math on offset coords. Convert to cube coordinates first — use hex_distance, which does this internally.
  - Treating direction indices as compass cardinals. There is no North/South — index 1 is Northeast, 2 is Northwest, 4 is Southwest, 5 is Southeast.
  - Iterating get_tiles_in_range and re-filtering by distance. The function already excludes the center and applies the radius cap; double-filtering is dead work.
  - Mutating DIRECTIONS_EVEN_ROW or DIRECTIONS_ODD_ROW. They are row-shape lookup tables, not state — treat as constants.
  - Assuming East/West shift between even and odd rows. Only the four diagonal directions (NE, NW, SW, SE) change; East is always (1, 0) and West is always (-1, 0).
```
