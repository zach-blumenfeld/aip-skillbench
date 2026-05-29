# Civ6 Placement Rules Reference (Gathering Storm)

Detailed placement rules for Civilization 6 districts. Load on demand when
validating a placement, debugging a `PlacementResult.errors` message, or
planning a placement by hand.

The authoritative implementation lives in
`scripts/placement_rules.py` — this file is the human-readable rule sheet
the code encodes.

## City Placement

### Minimum distance between city centers

| Condition             | Min center-to-center distance | Tiles between |
| --------------------- | ----------------------------- | ------------- |
| Same landmass         | 4 tiles                       | 3 tiles       |
| Different landmasses  | 3 tiles                       | 2 tiles       |

### Invalid settlement tiles

- Water (Coast, Ocean, Lake)
- Mountains
- Natural Wonders

### City Center on special tiles

Settling a City Center on a tile with Geothermal Fissure or
Luxury/Strategic Resources **preserves** them — they remain on the tile
and continue to provide adjacency bonuses to neighbouring districts.
Districts other than City Center may NOT be placed on those tiles.

## District Placement

### Universal rules (apply to every district)

| Rule                 | Description                                                                       |
| -------------------- | --------------------------------------------------------------------------------- |
| Distance             | Within **3 tiles** of the City Center                                             |
| Mountains            | Cannot place                                                                      |
| Natural Wonders      | Cannot place                                                                      |
| Strategic Resources  | Cannot place (Iron, Horses, Niter, Coal, Oil, Aluminum, Uranium)                  |
| Luxury Resources     | Cannot place                                                                      |
| Existing district    | Cannot stack — tile must be unoccupied                                            |
| Bonus Resources      | CAN place (resource is destroyed)                                                 |
| Woods/Rainforest/Marsh | CAN place (feature is destroyed)                                                |

### District-specific rules

| District       | Special requirement                                                              |
| -------------- | --------------------------------------------------------------------------------- |
| Harbor         | Must be on Coast/Lake, adjacent to land                                          |
| Water Park     | Must be on Coast/Lake, adjacent to land                                          |
| Aerodrome      | Must be on flat land (no hills/water/mountain)                                   |
| Spaceport      | Must be on flat land                                                             |
| Encampment     | NOT adjacent to City Center                                                      |
| Preserve       | NOT adjacent to City Center                                                      |
| Aqueduct       | Adjacent to City Center AND adjacent to fresh water (Mountain, River, Lake, Oasis); "No U-Turn" — fresh water cannot only be on the City-Center edge |
| Dam            | On Floodplains, river must traverse ≥2 hex edges                                 |
| Canal          | Adjacent to ≥1 water body AND (adjacent to City Center OR to a SECOND, separate water body) |

## District Limits

### Population formula

```
max_specialty_districts = 1 + floor((population - 1) / 3)
```

| Population | Max specialty districts |
| ---------- | ----------------------- |
| 1–3        | 1                       |
| 4–6        | 2                       |
| 7–9        | 3                       |
| 10–12      | 4                       |

### Non-specialty districts (DO NOT count toward the limit)

These may be built regardless of population:

- Aqueduct / Bath
- Neighborhood / Mbanza
- Canal
- Dam
- Spaceport

### Uniqueness rules

| Rule                     | Districts                                                                                                                                              |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ONE per city             | Campus, Holy Site, Theater Square, Commercial Hub, Harbor, Industrial Zone, Entertainment Complex, Water Park, Encampment, Aerodrome, Preserve         |
| Multiple per city        | Neighborhood (plus non-specialty: Aqueduct, Dam, Canal, Spaceport)                                                                                     |
| ONE per civilization     | Government Plaza, Diplomatic Quarter                                                                                                                   |

## Destruction effects

Placing ANY non-City-Center district destroys, on its target tile:

- Woods (`FEATURE_FOREST`)
- Rainforest (`FEATURE_JUNGLE`)
- Marsh (`FEATURE_MARSH`)
- Bonus Resources

City Center is the exception — it preserves features and resources on
its own tile.

These destructions cascade: a tile that contributed +0.5 (Woods) to a
neighbouring Holy Site no longer counts once a district is placed on it.
`AdjacencyCalculator.apply_destruction()` materialises this side-effect
before adjacency is calculated.

## Validation checklist

1. Within 3 of the City Center?
2. Not a mountain / natural wonder / geothermal fissure?
3. Not a strategic / luxury resource?
4. Tile unoccupied (no other district or City Center)?
5. District-specific requirement satisfied (water, flat land, etc.)?
6. City has a specialty-district slot left (population formula)?
7. District is not already built somewhere it must be unique?
