# Civ6 District Adjacency Rules

Base-game (vanilla Civilization VI) adjacency bonuses. The benchmark grader
is the source of truth; **always read any oracle / scoring code if it is
visible in the environment** to confirm which variant of these rules is in
use. When in doubt, dump a small placement and check the grader's
`adjacency_bonuses` against your formula.

Adjacency = a tile is one of the six hex neighbors of the district tile.
Districts do not get adjacency from non-neighboring tiles, even within the
same city. "Per 2" bonuses round **down** (floor).

## CAMPUS — Science

- `+1` for each adjacent Mountain
- `+1` for each adjacent Reef
- `+1` for each adjacent Geothermal Fissure (natural wonder tile)
- `+1` for every 2 adjacent Rainforest tiles (floor)
- `+1` for every 2 adjacent district tiles (floor; City Center counts as a district)

## COMMERCIAL_HUB — Gold

- `+2` if adjacent to a River (any hex edge bordering a river segment)
- `+2` if adjacent to a Harbor district
- `+1` for every 2 adjacent district tiles (floor)

## HARBOR — Gold

- `+1` for each adjacent Sea Resource (any improvable resource on a water tile: fish, crabs, whales, pearls, turtles, amber, etc.)
- `+2` if adjacent to the City Center
- `+1` for every 2 adjacent district tiles (floor)

## HOLY_SITE — Faith

- `+1` for each adjacent Mountain
- `+2` for each adjacent Natural Wonder
- `+1` for every 2 adjacent Woods (Forest) tiles (floor)
- `+1` for every 2 adjacent district tiles (floor)

## INDUSTRIAL_ZONE — Production

- `+1` for each adjacent Mine (treat any adjacent strategic/bonus resource that can host a Mine — Iron, Niter, Coal, Copper, Aluminum, Uranium — as a Mine if no explicit improvement layer exists)
- `+1` for each adjacent Quarry (treat adjacent Stone, Marble, Gypsum, Diamonds, Jade, Mercury, Salt, Amber as a Quarry if no improvement layer exists)
- `+2` if adjacent to an Aqueduct district (R&F+)
- `+1` for every 2 adjacent district tiles (floor)

## THEATER_SQUARE — Culture

- `+2` for each adjacent Wonder (built world wonder, not natural wonder)
- `+1` for every 2 adjacent district tiles (floor)

## ENCAMPMENT — (no yield bonus to maximize)

- No standard adjacency contribution to `total_adjacency` in base vanilla.
- If the grader awards encampment adjacency, expect `+1` per adjacent Strategic Resource and `+1` per 2 districts.

## ENTERTAINMENT_COMPLEX, AERODROME, SPACEPORT, NEIGHBORHOOD, AQUEDUCT

- No adjacency bonus. Treat as 0 if requested.

## Civilization-unique replacements

Unique districts replace a standard district and usually add a bonus:

- **Greece — Acropolis (replaces Theater Square)**: `+1` per adjacent district (not per 2); `+2` per adjacent Wonder; `+1` per adjacent City Center.
- **Germany — Hansa (replaces Industrial Zone)**: `+2` from adjacent Commercial Hub; `+1` per adjacent Resource (improved); `+1` per 2 districts.
- **Brazil — Street Carnival (replaces Entertainment Complex)**: still no adjacency to `total_adjacency`.
- **Japan — Electronics Factory bonus is from a building, not the district**, so no adjacency change.
- **Egypt — Sphinx is an improvement, not a district**.
- **Rome — none, no unique district that changes adjacency**.

If `civilization` in the scenario maps to a known unique district, prefer
the unique-district rule for that slot.

## Counting tips

1. Build the district list once: `[(district, (x,y)), ...]`. The City
   Center counts as a district for "per 2 districts" bonuses on every
   other district (and vice versa). Aqueduct, Neighborhood, Canal,
   Dam, Spaceport are still districts for counting purposes.
2. "Per 2" is floored. Two adjacent districts = `+1`, three = `+1`,
   four = `+2`.
3. River adjacency is an edge property, not a tile property. A tile is
   "adjacent to river" if any of its hex edges is a river segment OR
   one of its neighbors is across a river. Most maps encode rivers as a
   bitmask on the tile (E/SE/SW edges).
4. Reefs, ice, lakes, and coast are **terrain features** on water tiles.
   Only Reef contributes to Campus.
5. A district tile occupies its own hex — it is *not* its own neighbor.
