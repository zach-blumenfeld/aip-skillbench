# .Civ6Map format and hex grid

Load when a map does not parse, `inspect-map` warns, or a coordinate needs hand-checking.

## The file

A `.Civ6Map` is a SQLite 3 database. Explore before trusting it:

```sql
SELECT name FROM sqlite_master WHERE type='table';   -- list tables
PRAGMA table_info(Plots);                             -- columns ('pk' = key order)
SELECT sql FROM sqlite_master WHERE name='Plots';     -- CREATE statement
PRAGMA index_list(Plots); PRAGMA index_info(<index>); -- unique keys
PRAGMA foreign_key_list(Plots);
SELECT * FROM Plots LIMIT 5; SELECT COUNT(*) FROM Plots;
SELECT DISTINCT TerrainType FROM Plots;               -- value vocabularies
SELECT COUNT(*) FROM PlotFeatures WHERE FeatureType IS NULL;
```

Tables used (all keyed by plot `ID`, LEFT-joined onto `Plots`; a missing table is treated as empty):

| Table | Columns used | Meaning |
|---|---|---|
| `Map` | Width, Height, WrapX | grid size; `x = ID % Width`, `y = ID // Width` |
| `Plots` | TerrainType, IsImpassable | `TERRAIN_GRASS`, `TERRAIN_PLAINS_HILLS`, `TERRAIN_GRASS_MOUNTAIN`, `TERRAIN_COAST`, `TERRAIN_OCEAN`... |
| `PlotFeatures` | FeatureType | `FEATURE_FOREST` (Woods), `FEATURE_JUNGLE` (Rainforest), `FEATURE_MARSH`, `FEATURE_REEF`, `FEATURE_GEOTHERMAL_FISSURE`, `FEATURE_FLOODPLAINS[_PLAINS/_GRASSLAND]`, `FEATURE_ICE`, natural wonders |
| `PlotResources` | ResourceType | `RESOURCE_IRON`...; classed STRATEGIC / LUXURY / BONUS by lookup |
| `PlotImprovements` | ImprovementType | `IMPROVEMENT_MINE`, `_QUARRY`, `_LUMBER_MILL`... |
| `PlotRivers` | IsWOfRiver, IsNWOfRiver, IsNEOfRiver | river along this plot's E / SE / SW edge |
| `StartPositions` | Plot, Type, Value | player start plots (also `Players.StartingPosition` "x,y") |
| `Cities`, `Districts` | Plot, DistrictType | pre-built cities / districts (`DISTRICT_CAMPUS`...) |

Parsing rules in `scripts/civ6map.py`:
- `TERRAIN_X_MOUNTAIN` -> terrain `MOUNTAIN`; `TERRAIN_X_HILLS` -> terrain `X`, `is_hills`.
- Floodplains features -> `is_floodplains=True`, feature cleared.
- Any feature not in the ordinary set is a natural wonder.
- Unknown resource -> treated as LUXURY (unbuildable) with a warning.
- Water bodies with no Ocean tile and at most 8 tiles -> `LAKE`.
- `FEATURE_ICE` or impassable non-mountain -> blocked for cities and districts.
- `NamedRiver` / `NamedRiverPlot` repeat the river data with Civ6's own edge enum
  (0=NE, 1=E, 2=SE, 3=SW, 4=W, 5=NW); `PlotRivers` is the source used.

## Hex grid (odd-r offset)

- Odd rows (`y % 2 == 1`) are shifted right by half a hex. Map `y` grows northward.
- Neighbor offsets, index order used by `hex_utils`:

| index | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| even row | (1,0) | (0,-1) | (-1,-1) | (-1,0) | (-1,1) | (0,1) |
| odd row | (1,0) | (1,-1) | (0,-1) | (-1,0) | (0,1) | (1,1) |

  hex_utils labels these E, NE, NW, W, SW, SE, i.e. with `y` growing downward. On a Civ6 map
  (`y` up) index 1 is really SE, 2 SW, 4 NW, 5 NE. Neighbor sets and distances are the same
  either way; only river-edge mapping needs the true geometry: IsWOfRiver -> index 0,
  IsNWOfRiver -> index 1, IsNEOfRiver -> index 2, mirrored onto the tile across the edge with
  `(index + 3) % 6`. This convention makes the map's river segments join up.
- Distance: convert to cube (`cx = col - (row - (row & 1)) // 2`, `cz = row`, `cy = -cx - cz`),
  distance = `(|dx| + |dy| + |dz|) / 2`. Adjacent iff distance 1.
- Tiles within radius r of a center: scan the (2r+1)^2 box, keep distance <= r (excludes the
  center): 6 at r=1, 18 at r=2, 36 at r=3.
- Examples: neighbors of (21,13) (odd) = (22,13), (22,12), (21,12), (20,13), (21,14), (22,14);
  `hex_distance(21,13, 24,13) = 3`.
- civ6lib hex math does not wrap on X even when `Map.WrapX` is 1; `inspect-map` warns when
  land lies near the seam.
