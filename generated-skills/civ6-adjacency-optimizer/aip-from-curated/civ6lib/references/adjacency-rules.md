# Civ6 Adjacency Bonus Reference (Gathering Storm)

Detailed adjacency bonus tables for Civilization 6 districts. Load on
demand when computing a bonus by hand, sanity-checking
`AdjacencyCalculator` output, or deciding which neighbouring features
matter for a candidate placement.

The authoritative implementation lives in
`scripts/adjacency_rules.py` — this file is the human-readable rule
sheet the code encodes.

## Critical rule — separate flooring for minor bonuses

Each `+0.5 per source` minor-bonus type is floored **independently**,
then the floored values are summed. Never sum the raw counts first.

```
WRONG:
  Industrial Zone with 1 Mine + 1 Lumber Mill + 1 District
  → (1 + 1 + 1) / 2 = floor(1.5) = 1   ❌

CORRECT:
  Mine        : floor(1 / 2) = 0
  Lumber Mill : floor(1 / 2) = 0
  District    : floor(1 / 2) = 0
  TOTAL = 0                              ✓
```

Final bonus is always an integer.

## Major + minor bonuses are additive

A district that grants a major bonus (e.g. Aqueduct → +2 Industrial
Zone) ALSO counts toward the generic `+0.5 per district` minor bonus.
The two are not mutually exclusive.

## Adjacency rules by district

### Campus (+Science)

| Bonus       | Source                                                |
| ----------- | ----------------------------------------------------- |
| +2 each     | Geothermal Fissure, Reef, Great Barrier Reef          |
| +1 each     | Mountain                                              |
| +1 each     | Government Plaza                                      |
| +0.5 each   | Rainforest (`FEATURE_JUNGLE`) — floor separately      |
| +0.5 each   | District — floor separately                           |

### Holy Site (+Faith)

| Bonus       | Source                                       |
| ----------- | -------------------------------------------- |
| +2 each     | Natural Wonder                               |
| +1 each     | Mountain                                     |
| +1 each     | Government Plaza                             |
| +0.5 each   | Woods (`FEATURE_FOREST`) — floor separately  |
| +0.5 each   | District — floor separately                  |

### Theater Square (+Culture)

| Bonus       | Source                              |
| ----------- | ----------------------------------- |
| +2 each     | Wonder (built)                      |
| +2 each     | Entertainment Complex, Water Park   |
| +1 each     | Government Plaza                    |
| +0.5 each   | District — floor separately         |

### Commercial Hub (+Gold)

| Bonus       | Source                                            |
| ----------- | ------------------------------------------------- |
| +2          | If the Commercial Hub tile itself is ON a river   |
| +2 each     | Adjacent Harbor                                   |
| +1 each     | Government Plaza                                  |
| +0.5 each   | District — floor separately                       |

### Harbor (+Gold)

| Bonus       | Source                                                  |
| ----------- | ------------------------------------------------------- |
| +2 each     | Adjacent City Center                                    |
| +1 each     | Coastal Resource (Fish, Crabs, Whales, Pearls, etc.)    |
| +1 each     | Government Plaza                                        |
| +0.5 each   | District — floor separately                             |

### Industrial Zone (+Production)

| Bonus       | Source                                                 |
| ----------- | ------------------------------------------------------ |
| +2 each     | Aqueduct, Bath, Dam, Canal                             |
| +1 each     | Quarry                                                 |
| +1 each     | Strategic Resource                                     |
| +1 each     | Government Plaza                                       |
| +0.5 each   | Mine — floor separately                                |
| +0.5 each   | Lumber Mill — floor separately                         |
| +0.5 each   | District — floor separately                            |

### Districts with NO adjacency bonuses

Entertainment Complex, Water Park, Encampment, Aerodrome, Spaceport,
Government Plaza, Preserve.

(These still count as a `+0.5 per district` source for other districts.)

## Government Plaza

Government Plaza gives **+1 adjacency** to any adjacent specialty
district (Campus, Holy Site, Theater Square, Commercial Hub, Harbor,
Industrial Zone) AND also counts toward the generic `+0.5 per district`
minor bonus.

## Which districts count for "+0.5 per District"

Every placed district counts as a District source, including
non-specialty ones:

Campus, Holy Site, Theater Square, Commercial Hub, Harbor,
Industrial Zone, Entertainment Complex, Water Park, Encampment,
Aerodrome, Spaceport, Government Plaza, Diplomatic Quarter, Preserve,
City Center, Aqueduct, Dam, Canal, Neighborhood.

## Destruction caveats

Placing any non-City-Center district destroys Woods, Rainforest, Marsh
and Bonus Resources on its tile. This affects the adjacency bonus of
OTHER districts:

- Holy Site loses its +0.5 Woods contribution if a district was built on
  the adjacent Woods tile.
- Industrial Zone loses bonus resources that were on an adjacent tile
  that is now a district.

Call `AdjacencyCalculator.apply_destruction(placements)` before counting
sources, or use `calculate_total_adjacency()` which does this for you.
