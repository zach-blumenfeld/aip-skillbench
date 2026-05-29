# `civ6lib` Library Usage

Reference for the Python modules that back this skill. All modules live
in `scripts/`. Add the `scripts/` directory to `sys.path` (or import
relative to it) before importing.

## Modules

- `scripts/placement_rules.py` — `DistrictType`, `Tile`, `PlacementRules`,
  `PlacementResult`, `validate_city_distances`,
  `validate_district_count`, `validate_district_uniqueness`,
  `calculate_max_specialty_districts`, `get_placement_rules`.
- `scripts/adjacency_rules.py` — `AdjacencyCalculator`, `AdjacencyRule`,
  `AdjacencyResult`, `DISTRICT_ADJACENCY_RULES`,
  `DISTRICTS_FOR_ADJACENCY`, `get_adjacency_calculator`.
- `scripts/hex_utils.py` — `get_neighbors`, `hex_distance`, `is_adjacent`,
  `get_direction_to_neighbor`, `get_tiles_in_range`,
  `get_opposite_direction`. Civ6 uses **odd-r** offset coordinates
  (odd rows shifted right).

## Minimal usage

```python
import sys
sys.path.insert(0, "scripts")

from placement_rules import (
    DistrictType, Tile, PlacementRules,
    get_placement_rules,
    validate_district_count, validate_district_uniqueness,
)
from adjacency_rules import (
    AdjacencyCalculator, get_adjacency_calculator,
)

# tiles: Dict[Tuple[int, int], Tile]
rules = get_placement_rules(tiles, city_center=(21, 13), population=7)

result = rules.validate_placement(
    DistrictType.CAMPUS, 21, 14,
    existing_placements={},   # Dict[(x, y), DistrictType]
)
if not result.valid:
    print("Errors:", result.errors)

calculator = get_adjacency_calculator(tiles)
total, per_district = calculator.calculate_total_adjacency(placements)
```

## Key types

### `DistrictType` (IntEnum)

`NONE`, `CITY_CENTER`, `CAMPUS`, `HOLY_SITE`, `THEATER_SQUARE`,
`COMMERCIAL_HUB`, `HARBOR`, `INDUSTRIAL_ZONE`,
`ENTERTAINMENT_COMPLEX`, `WATER_PARK`, `ENCAMPMENT`, `AERODROME`,
`GOVERNMENT_PLAZA`, `DIPLOMATIC_QUARTER`, `PRESERVE`, `AQUEDUCT`,
`DAM`, `CANAL`, `SPACEPORT`, `NEIGHBORHOOD`.

`DISTRICT_NAME_MAP` maps the string name back to the enum.

### `Tile` (dataclass)

Fields: `x`, `y`, `terrain`, `feature`, `is_hills`, `is_floodplains`,
`river_edges` (list of 0–5), `river_names`, `resource`, `resource_type`
(`"STRATEGIC" | "LUXURY" | "BONUS"`), `improvement`
(`"MINE" | "QUARRY" | "LUMBER_MILL" | …`).

Convenience properties: `is_water`, `is_coast`, `is_lake`, `is_mountain`,
`is_natural_wonder`, `has_river`, `is_flat_land`.

### `PlacementResult` (dataclass)

`valid: bool`, `errors: List[str]`, `warnings: List[str]`. Warnings
flag destruction effects (feature/bonus-resource loss) — placement is
still legal.

### `AdjacencyResult` (dataclass)

`total_bonus: int` (already floored), `breakdown: Dict[str, dict]` —
the breakdown shows per-rule `count`, `bonus`, `count_required`,
`bonus_per`, and the concrete `sources` list. Use it to debug surprising
totals.

## Calling conventions

- `placements` is `Dict[Tuple[int, int], DistrictType]` — coordinates
  keyed first. `Tile` lookups in the library use the same key shape.
- `existing_placements` passed to `validate_placement` is the same
  `Dict[Tuple[int, int], DistrictType]` — pass everything already on
  the map (including City Center) so adjacency and occupancy checks
  resolve correctly.
- `validate_district_count` takes `Dict[district_name_string, Tuple[int, int]]`
  (string-keyed). The library uses both shapes; check the function
  signature before passing.
- `calculate_total_adjacency` applies destruction *before* counting
  sources. Don't pre-mutate `tiles`; pass the original.

## Extending for civilization uniques

Subclass `PlacementRules` and override
`_validate_civilization_specific(...)` to add per-civ unique-district
rules without re-implementing the base checks.
