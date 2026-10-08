Turn this request into the parameters for the distance computation.

Request:
{task}

Already decided: extreme = {extreme}, boundary_scope = {boundary_scope}.

Produce JSON with exactly these keys:

- `earthquakes_path` — absolute path to the earthquake GeoJSON (USGS FeatureCollection; Point coordinates are [lon, lat, depth_km], `properties.time` is epoch ms). Use the location the request gives. If it names only a file name, look in the working directory and then /root/ (where the task container usually puts them, e.g. /root/earthquakes_2024.json) and pass the absolute path.
- `plates_path` — absolute path to the PB2002 plate polygons GeoJSON (properties `Code`, `PlateName`), e.g. /root/PB2002_plates.json.
- `boundaries_path` — absolute path to the PB2002 boundary lines GeoJSON (properties `Name` like "PA-NA", `PlateA`, `PlateB`), e.g. /root/PB2002_boundaries.json.
- `plate` — the target plate as the request names it: a PB2002 code (`PA`) or a name (`Pacific`). The script resolves either against the file; load the codes reference only if the request uses an unusual alias.
- `filters` — object; include only constraints the request states and the file does not already guarantee: `min_magnitude`, `max_magnitude`, `start_time`, `end_time` (ISO date, end exclusive, UTC), `event_type` (e.g. "earthquake"). Use an empty object when there are none. Do not invent a filter from the file name alone.
- `output_path` — where the answer must be written, made absolute (resolve a relative path against the working directory the task runs in), or "" if the request only wants it reported.
- `output_spec` — the request's output requirements copied verbatim: file format, exact key names, units, rounding, time format. "" if none are stated.
