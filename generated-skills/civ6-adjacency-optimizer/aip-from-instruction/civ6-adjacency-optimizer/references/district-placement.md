# District Placement Constraints

A placement is **invalid** (score → 0) if any of these rules are broken.
Validate every placement before writing `/output/scenario_N.json`.

## City Center

- Must be on land (not on water terrain).
- Must not be on a mountain.
- Must not be on a natural wonder.
- Typically must not be on a tile occupied by a feature that blocks
  settlement; in practice for this benchmark, ensure the tile terrain is
  one of: Grassland, Plains, Desert, Tundra, Snow (flat or hills).
- If `num_cities > 1`, cities must be ≥ 4 tiles apart (Civ6 default
  minimum city distance is 3 hexes between centers; safest is ≥ 4).

## District work range

- Districts must be placed within **3 hexes** of one of the city centers
  they belong to (the "workable tile" range).
- The district tile itself must be inside the city's borders. For this
  benchmark, treat "within 3 hexes of the city center" as the working
  border.
- A tile can host **at most one district / city center**. No two
  placements share a coordinate.

## Per-district terrain rules

| District             | Allowed terrain                                                                                                  | Disallowed                                       |
|----------------------|------------------------------------------------------------------------------------------------------------------|--------------------------------------------------|
| CAMPUS               | Any flat or hills land tile (not mountain, not water)                                                            | Mountains, water, natural wonders, lava          |
| COMMERCIAL_HUB       | Any flat or hills land tile                                                                                       | Mountains, water, natural wonders                |
| HOLY_SITE            | Any flat or hills land tile                                                                                       | Mountains, water, natural wonders                |
| THEATER_SQUARE       | Any flat or hills land tile                                                                                       | Mountains, water, natural wonders                |
| INDUSTRIAL_ZONE      | Any flat or hills land tile                                                                                       | Mountains, water, natural wonders                |
| ENCAMPMENT           | Any flat or hills land tile, must NOT be adjacent to City Center                                                  | Mountains, water, adjacent to city center        |
| ENTERTAINMENT_COMPLEX| Any flat or hills land tile                                                                                       | Mountains, water                                 |
| AERODROME            | Flat land only (no hills)                                                                                         | Hills, mountains, water                          |
| SPACEPORT            | Flat land only                                                                                                    | Hills, mountains, water                          |
| HARBOR               | Coast water tile (shallow water), must be adjacent to land AND adjacent to the City Center                       | Land tiles, deep ocean, mountains                |
| AQUEDUCT             | Land tile adjacent to City Center AND adjacent to (River edge OR Lake OR Oasis OR Mountain)                       | Tiles not adjacent to city center                |
| NEIGHBORHOOD         | Any flat or hills land tile                                                                                       | Mountains, water                                 |

- **Features that block districts** (must be removed before building; for
  optimization treat the tile as available but lose the feature):
  Woods, Rainforest, Marsh. For this benchmark, **assume features
  remain** — Holy Site / Campus may still want them as adjacent neighbors,
  so prefer to place the district on a feature-free tile and keep
  adjacent woods/rainforest intact.
- **Resources** generally do not block district placement, but the
  resource yield is lost. For optimization treat resources as adjacent
  only, not the district tile itself.

## District limit by population

City may build at most `floor((population + 2) / 3)` specialty districts
(those counting toward the cap). For the benchmark:

| Population | Specialty district cap |
|------------|-----------------------|
| 1–2        | 1                     |
| 3–5        | 2                     |
| 6–9        | 3                     |
| 10–12      | 4                     |
| 13–15      | 5                     |
| 16+        | 6                     |

**Uncapped districts** (don't count toward the limit): Aqueduct,
Neighborhood, Canal, Dam, Spaceport, City Center.

Building only specialty (capped) districts gives the highest adjacency
density. Build to the cap, not beyond.

## Sanity checklist before emitting JSON

1. Each placement coordinate is unique (no two districts on the same tile).
2. Each placement is within 3 hexes of at least one city center.
3. Each placement satisfies its per-district terrain rule.
4. Specialty district count per city ≤ population cap.
5. Number of city centers exactly equals `num_cities`.
6. `sum(adjacency_bonuses.values()) == total_adjacency`.
7. JSON keys exactly match the format in `instruction.md`
   (single-city vs multi-city).
