Write the final answer from the computed result. Do not recompute any value by hand; the only change allowed is rounding or unit/format conversion the request asks for.

Request:
{task}

Output path: {output_path}
Output requirements (verbatim from the request): {output_spec}

Plate: {plate_code} ({plate_name}); selection: {extreme} earthquake from the plate's boundaries (scope: {boundary_scope}).
Computed result (the chosen earthquake): {result}
Runner-up candidates, best first (id, distance_km, magnitude, latitude, longitude): {ranking}
Stats: {stats}
Method: {method}
Warnings: {warnings}

Rules:
1. Values come from `result`. Key mapping: id -> `id` (USGS event id, e.g. "us6000abcd"), place -> `place`, time -> ISO-8601 UTC string (`time_ms` holds the raw epoch ms if the request wants that), magnitude -> `mag`/`magnitude`, latitude/longitude in degrees, depth_km in km, distance_km in kilometres.
2. If `output_spec` names keys, use exactly those names, in that order, and nothing it forbids. Apply only the rounding it asks for; otherwise keep full precision for distance_km (do not round to whole km).
3. If no format is specified (including "just tell me" requests), use one JSON object with keys id, place, time, magnitude, latitude, longitude, distance_km.
4. If `output_path` is non-empty, write the file there (create parent dirs), then read it back and parse it to confirm it is valid and matches the spec. Write JSON numbers as numbers, not strings.
5. If `warnings` mention a tie or a polygon repair, mention it in your reply but still write the single top result.

Return JSON with keys `answer` (the object you wrote or would report) and `output_path` (the path written, or "").
