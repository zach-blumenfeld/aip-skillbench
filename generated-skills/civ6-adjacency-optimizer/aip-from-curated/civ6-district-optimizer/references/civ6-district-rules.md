# Civ6 district rules (Gathering Storm), as civ6lib implements them

The scripts import civ6lib verbatim (`scripts/civ6lib/`), so these tables are what
`optimize.py` and `verify_answer.py` enforce. Load this file to explain a result,
hand-check a placement, or adapt an answer the scripts could not parse.

## City placement

| Condition | Min distance (center to center) | Tiles between |
|-----------|------|------|
| Same landmass | 4 | 3 |
| Different landmasses | 3 | 2 |

Same landmass = reachable over land tiles (BFS); civ6lib's simplification of the game's area IDs.

Cannot settle on: water (Coast, Ocean, Lake), Mountains, Natural Wonders. The scripts also refuse
ice / impassable tiles.

A City Center settled on a Geothermal Fissure or a Luxury/Strategic resource **keeps** it: it
still gives adjacency to nearby districts. City Center destroys nothing. Districts can never
be placed on those tiles.

## District placement

All districts:

| Rule | |
|------|---|
| Distance | within **3 tiles** of its City Center |
| Mountains, Natural Wonders, Geothermal Fissure | cannot place |
| Strategic resources (Iron, Horses, Niter, Coal, Oil, Aluminum, Uranium) | cannot place |
| Luxury resources | cannot place |
| Existing district | cannot place on an occupied tile |
| Bonus resources | CAN place (resource destroyed) |
| Woods / Rainforest / Marsh | CAN place (feature destroyed) |
| Land districts | cannot be on water |

District-specific:

| District | Requirement |
|----------|-------------|
| Harbor, Water Park | on Coast or Lake, adjacent to land |
| Aerodrome, Spaceport | flat land (no hills, water, mountain) |
| Encampment, Preserve | NOT adjacent to City Center |
| Aqueduct | adjacent to City Center AND to fresh water (Mountain, River, Lake, Oasis; a river on its own tile counts). No U-Turn: if the only fresh water is a river on the edge it shares with the City Center, invalid |
| Dam | on Floodplains, river along 2+ of its edges |
| Canal | adjacent to water (Coast/Ocean/Lake) AND either adjacent to the City Center or touching two separate (mutually non-adjacent) water tiles |

## District limits

`max_specialty_districts = 1 + floor((population - 1) / 3)`

| Population | 1-3 | 4-6 | 7-9 | 10-12 |
|---|---|---|---|---|
| Max specialty districts | 1 | 2 | 3 | 4 |

Do not count toward the limit (non-specialty): Aqueduct / Bath, Neighborhood / Mbanza, Canal,
Dam, Spaceport (and the City Center).

Uniqueness: ONE per city — Campus, Holy Site, Theater Square, Commercial Hub, Harbor, Industrial
Zone, Entertainment Complex, Water Park, Encampment, Aerodrome, Preserve. Multiple per city —
Neighborhood (and Aqueduct, Dam, Canal, Spaceport in civ6lib). ONE per civilization — Government
Plaza, Diplomatic Quarter. The answer format `{district_name: [x, y]}` holds one of each name,
so the optimizer places at most one of every type.

## Adjacency

**Minor (+0.5) bonuses are floored per source type, separately, then summed.**
IZ next to 1 Mine + 1 Lumber Mill + 1 District = 0 + 0 + 0 = **0**, not floor(3/2) = 1.
Final bonuses are integers. Major and minor bonuses add: an Aqueduct next to an IZ gives +2 and
also counts as a district for the +0.5.

| District | +2 each | +1 each | +0.5 each (floor per type) |
|---|---|---|---|
| Campus (science) | Geothermal Fissure, Reef, Great Barrier Reef | Mountain, Government Plaza | Rainforest; District |
| Holy Site (faith) | Natural Wonder | Mountain, Government Plaza | Woods; District |
| Theater Square (culture) | built Wonder; Entertainment Complex, Water Park | Government Plaza | District |
| Commercial Hub (gold) | Harbor; **+2 once if its own tile is on a river** | Government Plaza | District |
| Harbor (gold) | City Center | Coastal resource (any resource on a water tile: Fish, Crabs, Whales, Pearls...), Government Plaza | District |
| Industrial Zone (production) | Aqueduct, Dam, Canal (Bath) | Quarry, Strategic resource, Government Plaza | Mine; Lumber Mill; District |

No adjacency of their own: Entertainment Complex, Water Park, Encampment, Aerodrome, Spaceport,
Government Plaza, Preserve (and Diplomatic Quarter, Aqueduct, Dam, Canal, Neighborhood).

Government Plaza gives +1 to each adjacent Campus, Holy Site, Theater Square, Commercial Hub,
Harbor, Industrial Zone, and also counts as a district for the +0.5.

Count as "District" for +0.5: Campus, Holy Site, Theater Square, Commercial Hub, Harbor,
Industrial Zone, Entertainment Complex, Water Park, Encampment, Aerodrome, Spaceport, Government
Plaza, Diplomatic Quarter, Preserve, City Center, Aqueduct, Dam, Canal, Neighborhood.

Each neighbor counts at most once per rule. Total adjacency = sum over all non-City-Center
districts.

## Destruction

Placing any district (not the City Center) destroys Woods (FEATURE_FOREST), Rainforest
(FEATURE_JUNGLE), Marsh (FEATURE_MARSH), bonus resources, and the tile's improvement. This
changes OTHER districts' adjacency (a Holy Site loses the Woods a Campus was built on), so
totals are always computed after destruction.

## civ6lib details that affect scores

- Natural wonders are detected by the substring `NATURAL_WONDER` in the feature name; the
  loader renames wonder features to `NATURAL_WONDER_<NAME>` (Great Barrier Reef ->
  `NATURAL_WONDER_GREAT_BARRIER_REEF`). civ6lib's Theater Square "WONDER" source is a
  substring match, so a Theater next to a natural wonder also gets +2.
- Feature sources match by substring or equality; improvements by name (`MINE`, `QUARRY`,
  `LUMBER_MILL`, the `IMPROVEMENT_` prefix stripped).
- "Bath" is listed in the IZ rule but is not a DistrictType; it never matches.
- Rivers: a tile is "on a river" if any of its six edges carries one (both tiles sharing
  the edge).

## Quick validation checklist

1. Tile within 3 of the City Center?
2. Not a mountain / natural wonder / geothermal fissure?
3. Not a strategic or luxury resource?
4. Unoccupied?
5. District-specific requirement met?
6. Specialty count within `1 + floor((pop-1)/3)`?
7. Unique district not already built (per city / per civilization)?
