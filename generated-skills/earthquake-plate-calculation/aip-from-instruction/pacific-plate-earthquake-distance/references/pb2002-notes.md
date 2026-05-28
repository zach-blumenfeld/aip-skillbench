# PB2002 dataset notes

The Bird (2003) **PB2002** plate-tectonic dataset is widely redistributed with
slightly different attribute names across copies. Load with this skill's
defaults first; if attribute filtering fails, check the columns and adjust.

## Plates (polygons)

Typical attribute columns (any of):

| Field                  | Holds                                  |
|------------------------|----------------------------------------|
| `Code` / `PLATE_ID`    | Two-letter code, e.g. `PA` for Pacific |
| `PlateName` / `Name`   | Human-readable name, e.g. `Pacific`    |

The Pacific plate is identified by **`PA`** (preferred) or by name containing
`Pacific`. `solve.py` tries both.

## Boundaries (lines)

Each line segment lies between two plates. Typical attributes:

| Field                       | Holds                                       |
|-----------------------------|---------------------------------------------|
| `Name` (e.g. `PA-NA`)       | Plate-pair code joined by `-`               |
| `PlateA` / `PlateB`         | Individual plate codes for each side        |
| `Type` (sometimes)          | `OSR`, `OTF`, `OCB`, etc. — boundary kind   |

Pacific-adjacent segments are those where `PlateA == 'PA'` or
`PlateB == 'PA'`, or where the `Name` matches the regex
`(^|[^A-Za-z])PA([^A-Za-z]|$)`.

## Antimeridian handling

PB2002 polygons that cross the antimeridian are usually stored as a
**MultiPolygon split at ±180°**, so shapely's `within` predicate works in
EPSG:4326 without further preprocessing. Distance computation in EPSG:4326
returns **degrees**, not metres — always reproject before measuring.

## CRS choice cheatsheet

| Use case                                          | CRS                                                   |
|---------------------------------------------------|-------------------------------------------------------|
| Pacific-wide distance measurement                 | `+proj=aeqd +lat_0=0 +lon_0=-160` (this skill's pick) |
| Atlantic-wide                                     | `+proj=aeqd +lat_0=0 +lon_0=-30`                      |
| Local distances (single small country)            | Local UTM zone                                        |
| Global *area* (not distance)                      | Equal Earth (EPSG:8857)                               |

Avoid Web Mercator (EPSG:3857) for distance — it is conformal, not equidistant,
and it has a seam at ±180° that breaks Pacific polygons.
