# Projection Choice for Pacific Plate Distance

## Why projection matters here

GeoPandas `Point.distance(LineString)` returns **planar** distance in the units
of the active CRS. In EPSG:4326 that is *degrees*, which is meaningless across
a basin that spans ~100° of latitude. You must project to a metric CRS first.

The Pacific plate adds two extra constraints:

1. **It crosses the antimeridian.** A CRS whose central meridian is at 0°
   (e.g., Web Mercator EPSG:3857, World Equidistant EPSG:54032) will split the
   plate at ±180° and either produce a degenerate polygon or two halves.
2. **It's huge** — roughly a third of Earth's surface. No projection preserves
   distance everywhere; pick one that's accurate where the answer is likely to
   land (mid-Pacific, far from any boundary).

## Recommended CRS

A Pacific-centered Lambert Azimuthal Equal Area (LAEA):

```
+proj=laea +lat_0=0 +lon_0=-160 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs
```

- Central meridian at 160°W places the Pacific plate squarely in the middle, so
  the polygon does not need to be split.
- LAEA preserves area exactly and distorts distances only mildly across the
  Pacific basin (a few percent at the rim).

Reasonable alternatives:

| CRS                                             | Notes                                                    |
|-------------------------------------------------|----------------------------------------------------------|
| `+proj=aeqd +lat_0=0 +lon_0=-160 +datum=WGS84`  | Azimuthal equidistant — exact distance *from* (0,-160). Distortion grows for distances measured between two off-center points. |
| `EPSG:3832` (WGS 84 / PDC Mercator)             | Pacific-centered, standard EPSG. Mercator inflates distances at high latitudes (×2 at ±60°) — biases the answer toward poleward earthquakes. |
| `+proj=cea +lon_0=-160 +datum=WGS84`            | Equal-area cylindrical, Pacific-centered. Solid second choice. |

Avoid: EPSG:3857, EPSG:4087, EPSG:54032, any UTM zone, and anything centered
on Greenwich. They all split the Pacific.

## Apply the CRS before any spatial op

Reprojecting *first*, then doing `within()` / `distance()`, dodges the
antimeridian issue regardless of how the source GeoJSON stored the polygon
(single ring with wrap, MultiPolygon split at 180°, etc.). `pyproj` handles the
projection densification.

```python
plates_proj = plates.to_crs(PACIFIC_CRS)
earthquakes_proj = earthquakes.to_crs(PACIFIC_CRS)
plate_poly = plates_proj.loc[target_idx].geometry
inside = earthquakes_proj[earthquakes_proj.within(plate_poly)]
inside["distance_m"] = inside.distance(plate_poly.boundary)
```

`plate_poly.boundary` is the closed ring of the plate; `Point.distance` against
it returns the perpendicular distance to the nearest boundary segment, which is
exactly what "distance to the plate boundary" means.
