You are writing the final answer for the `{meta.name}` procedure. The
geospatial pipeline has already run; your job is to turn its numeric result
into a short, faithful natural-language reply to the user's original
question.

## Original request

{request}

## Pipeline result

- Target plate (PB2002 code): `{plate_code}`
- Extremum requested: `{extremum}`
- How many earthquakes landed inside the plate (via `.within()` on the
  projected EPSG:4087 geometry): `{count_in_plate}`
- Top `{top_n}` picks (ranked by `distance_km` to the plate's boundary):

```json
{top_results}
```

## How to write the summary

- Lead with the headline earthquake: its `distance_km` (round to one decimal),
  its `latitude` / `longitude`, and any identifying fields present in the
  record (common ones: `id`, `place`, `mag` or `magnitude`, `time`,
  `depth`). Only mention fields that are actually present in the record —
  do not invent values.
- Say it is "`{extremum}` from the plate boundary", not "from the center".
- If `top_n` is greater than 1, list the remaining picks after the headline
  as a short bulleted list in rank order.
- If `count_in_plate` is 0, say plainly that no earthquakes in the input fell
  inside plate `{plate_code}` and do not fabricate a result.
- Keep it to a short paragraph plus (optionally) a short list. No preamble,
  no caveats about methodology — the pipeline already enforces projection
  to EPSG:4087 and `.within()`-based membership.

## Output

Return a single JSON object:

```json
{{
  "summary": "<the natural-language answer>",
  "top_results": <passthrough of the pipeline's top_results list>,
  "count_in_plate": {count_in_plate},
  "plate_code": "{plate_code}"
}}
```

Return the JSON object only. No surrounding prose, no code fences.
