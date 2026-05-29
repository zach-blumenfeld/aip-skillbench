# Civ6 District Adjacency Bonus Rules (Gathering Storm)

Authoritative bonus tables and the per-source-floor math. The same rules
are encoded in `scripts/adjacency_rules.py`; this document is the
human-readable reference and is the safest place to look when a computed
total looks wrong.

## Critical Rule: Minor Bonus Counting

**Each +0.5 source type is counted SEPARATELY, then floored, then summed.**
Do NOT pool minor sources together before flooring.

```
WRONG:
  Industrial Zone with 1 Mine + 1 Lumber Mill + 1 District
  = floor((1 + 1 + 1) / 2) = 1   ❌

CORRECT:
  Mine:        floor(1 / 2) = 0
  Lumber Mill: floor(1 / 2) = 0
  District:    floor(1 / 2) = 0
  TOTAL = 0                       ✓
```

The final adjacency total is always an integer.

## Major and Minor Bonuses Are Additive

Districts that grant a *major* bonus (e.g., Aqueduct → IZ at +2) ALSO
count toward the generic "+0.5 per adjacent district" minor bonus. Don't
double-discount.

## Adjacency Rules by District

### Campus (+Science)

| Bonus | Source |
|-------|--------|
| +2 each | Geothermal Fissure, Reef, Great Barrier Reef |
| +1 each | Mountain |
| +1 each | Adjacent Government Plaza |
| +0.5 each | Rainforest (floor separately) |
| +0.5 each | District (floor separately) |

### Holy Site (+Faith)

| Bonus | Source |
|-------|--------|
| +2 each | Natural Wonder |
| +1 each | Mountain |
| +1 each | Adjacent Government Plaza |
| +0.5 each | Woods (floor separately) |
| +0.5 each | District (floor separately) |

### Theater Square (+Culture)

| Bonus | Source |
|-------|--------|
| +2 each | Built Wonder |
| +2 each | Entertainment Complex, Water Park |
| +1 each | Adjacent Government Plaza |
| +0.5 each | District (floor separately) |

### Commercial Hub (+Gold)

| Bonus | Source |
|-------|--------|
| +2 | If tile is ON a river (binary — once, not per edge) |
| +2 each | Adjacent Harbor |
| +1 each | Adjacent Government Plaza |
| +0.5 each | District (floor separately) |

### Harbor (+Gold)

| Bonus | Source |
|-------|--------|
| +2 each | Adjacent City Center |
| +1 each | Coastal Resource (Fish, Crabs, Whales, Pearls) |
| +1 each | Adjacent Government Plaza |
| +0.5 each | District (floor separately) |

### Industrial Zone (+Production)

| Bonus | Source |
|-------|--------|
| +2 each | Aqueduct, Bath, Dam, Canal |
| +1 each | Quarry |
| +1 each | Strategic Resource |
| +1 each | Adjacent Government Plaza |
| +0.5 each | Mine (floor separately) |
| +0.5 each | Lumber Mill (floor separately) |
| +0.5 each | District (floor separately) |

### Districts With NO Adjacency Bonuses

- Entertainment Complex
- Water Park
- Encampment
- Aerodrome
- Spaceport
- Government Plaza
- Preserve

## Government Plaza Adjacency

Government Plaza grants **+1** adjacency to every adjacent specialty
district that *does* receive adjacency bonuses:

- Campus, Holy Site, Theater Square, Commercial Hub, Harbor,
  Industrial Zone

Government Plaza also counts toward the generic "+0.5 per district"
minor bonus.

## Districts Counted for "+0.5 per District"

ALL of the following count, including non-specialty districts:

Campus, Holy Site, Theater Square, Commercial Hub, Harbor,
Industrial Zone, Entertainment Complex, Water Park, Encampment,
Aerodrome, Spaceport, Government Plaza, Diplomatic Quarter, Preserve,
City Center, Aqueduct, Dam, Canal, Neighborhood.

## Destruction Effects on Adjacency

Placing any non-City-Center district destroys:

- Woods (`FEATURE_FOREST`)
- Rainforest (`FEATURE_JUNGLE`)
- Marsh (`FEATURE_MARSH`)
- Bonus Resources

This affects adjacency for *other* districts on neighboring tiles —
e.g., placing a Commercial Hub on a Woods tile removes the Woods
contribution to any adjacent Holy Site's bonus. The Python calculator
applies destruction before counting sources; manual calculations must
do the same.

## Commercial Hub River Bonus (Special)

The +2 river bonus for Commercial Hub is awarded **once** if the CH tile
itself has any river edge. It is NOT per adjacent river tile.
