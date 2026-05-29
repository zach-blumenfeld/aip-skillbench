# Civ6 District Placement Rules (Gathering Storm)

Authoritative table of placement constraints. The same rules are enforced
programmatically in `scripts/placement_rules.py`; this document is the
human-readable reference for understanding *why* a placement is or isn't
legal.

## City Placement Rules

### Minimum Distance Between Cities

| Condition | Min Distance | Tiles Between |
|-----------|--------------|---------------|
| Same landmass | 4 tiles | 3 tiles |
| Different landmasses | 3 tiles | 2 tiles |

### Invalid Settlement Tiles

- Water (Coast, Ocean, Lake)
- Mountains
- Natural Wonders

### City Center Feature/Resource Preservation

Settling a City Center on a tile with Geothermal Fissure or
Luxury/Strategic Resources **preserves** them — they remain and provide
adjacency bonuses to nearby districts. Districts (not City Center) cannot
be placed on these tiles.

## Universal District Placement Rules

| Rule | Description |
|------|-------------|
| Distance | Within **3 tiles** of City Center |
| Mountains | Cannot place |
| Natural Wonders | Cannot place |
| Strategic Resources | Cannot place (Iron, Horses, Niter, Coal, Oil, Aluminum, Uranium) |
| Luxury Resources | Cannot place |
| Existing District | Cannot place on occupied tile |
| Bonus Resources | CAN place (resource destroyed) |
| Woods/Rainforest/Marsh | CAN place (feature destroyed) |
| Geothermal Fissure | Cannot place |

## District-Specific Placement Rules

| District | Special Requirement |
|----------|---------------------|
| Harbor | Must be on Coast/Lake, adjacent to land |
| Water Park | Must be on Coast/Lake, adjacent to land |
| Aerodrome | Must be on flat land (no hills, no water, no mountains) |
| Spaceport | Must be on flat land |
| Encampment | NOT adjacent to City Center |
| Preserve | NOT adjacent to City Center |
| Aqueduct | Adjacent to City Center AND fresh water (Mountain, River, Lake, Oasis). "No U-Turn" rule: fresh water cannot be only on the City Center edge. |
| Dam | On Floodplains, river crosses 2+ edges of the hex |
| Canal | Adjacent to at least one water body AND (adjacent to City Center OR connecting two separate water bodies) |

## District Population Limit

Specialty district cap as a function of city population:

```
max_specialty_districts = 1 + floor((population - 1) / 3)
```

| Population | Max Specialty Districts |
|------------|-------------------------|
| 1–3 | 1 |
| 4–6 | 2 |
| 7–9 | 3 |
| 10–12 | 4 |
| 13–15 | 5 |

### Non-Specialty Districts (Don't Count Toward Limit)

These can be built regardless of population cap:

- Aqueduct / Bath
- Neighborhood / Mbanza
- Canal
- Dam
- Spaceport
- City Center

## Uniqueness Rules

| Rule | Districts |
|------|-----------|
| ONE per city | Campus, Holy Site, Theater Square, Commercial Hub, Harbor, Industrial Zone, Entertainment Complex, Water Park, Encampment, Aerodrome, Preserve |
| Multiple per city | Neighborhood, Aqueduct, Dam, Canal, Spaceport |
| ONE per civilization | Government Plaza, Diplomatic Quarter |

## Feature & Resource Destruction Effects

Placing ANY non-City-Center district destroys:

- Woods (`FEATURE_FOREST`)
- Rainforest (`FEATURE_JUNGLE`)
- Marsh (`FEATURE_MARSH`)
- Bonus Resources

This affects adjacency bonuses for *other* districts — e.g., placing a
district on a Woods tile removes that Woods' Holy Site adjacency
contribution.

## Quick Validation Checklist

1. Is the tile within 3 of City Center?
2. Is the tile NOT a Mountain / Natural Wonder / Geothermal Fissure?
3. Is the tile NOT on a Strategic / Luxury resource?
4. Is the tile unoccupied by another district?
5. Does the district meet its special requirements (water, flat, adjacency)?
6. Does the city still have a specialty-district slot available?
7. Is the district unique and not already built (per-city or per-civ)?
