# Expected Data Formats

## earthquakes_2024.json

A GeoJSON `FeatureCollection` in USGS form. Each feature:

- `id` (top-level on the Feature, not in properties) — canonical event id, e.g. `"us6000mzvb"`.
- `properties.time` — milliseconds since Unix epoch (UTC). Convert with
  `datetime.fromtimestamp(ms / 1000, tz=timezone.utc)` and format as
  `"%Y-%m-%dT%H:%M:%SZ"`.
- `properties.mag` — magnitude, float.
- `properties.place` — human description, string.
- `geometry.coordinates` — `[longitude, latitude, depth_km]`. Read with shapely;
  the depth coordinate is ignored for surface-projection distance.

`geopandas.read_file` may drop the Feature-level `id`. Parse the JSON manually
(see `scripts/solve.py::load_geojson_as_gdf`) to preserve it.

## PB2002_plates.json

GeoJSON `FeatureCollection` of plate polygons from Peter Bird (2003). Common
attribute fields:

- `PlateName` or `Name` — full name, e.g. `"Pacific"`, `"North America"`.
- `Code` or `PB2002` — two-letter code, e.g. `"PA"` for Pacific, `"NA"` for
  North America.

Column naming varies across redistributions; resolve defensively (look up by
name first, then by code). The Pacific plate is `Pacific` / `PA`.

The Pacific plate polygon crosses the antimeridian (±180°). Some redistributions
store it as a single ring with longitudes that wrap; others use a `MultiPolygon`
split at 180°. Reproject to a Pacific-centered CRS before any spatial operation
to side-step both shapes.

## PB2002_boundaries.json

GeoJSON `FeatureCollection` of plate boundary lines. The geometry is identical
to the union of `plate.boundary` for the participating plates, so for this task
you can ignore this file and use `plate.boundary` directly. Boundary features
often carry attributes like `"PlateA"` / `"PlateB"` or a slash-delimited
`"BoundaryType"` (`"PA\\NA"`) if you need to filter to only Pacific segments.

## Output: /root/answer.json

Required fields, in this exact form:

```json
{
  "id": "us6000mzvb",
  "place": "...",
  "time": "2024-06-15T12:34:56Z",
  "magnitude": 5.4,
  "latitude": -10.123,
  "longitude": -155.456,
  "distance_km": 1234.56
}
```

- `time` is ISO 8601 with a trailing `Z`, second precision.
- `distance_km` is rounded to exactly 2 decimal places.
- `latitude`/`longitude` come from the earthquake point geometry in EPSG:4326.
