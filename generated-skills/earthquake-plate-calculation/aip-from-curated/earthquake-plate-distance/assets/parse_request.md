You are the first step of the `{meta.name}` procedure. Extract the structured
parameters that the downstream `compute` script needs, and pass the data-file
paths through unchanged.

## User's request

{request}

## Data files already located (pass through verbatim)

- `plates_path`: {plates_path}
- `boundaries_path`: {boundaries_path}
- `earthquakes_path`: {earthquakes_path}

## What to extract

Return a single JSON object with exactly these keys:

```json
{{
  "request": "<the original request, verbatim>",
  "plates_path": "<passthrough>",
  "boundaries_path": "<passthrough>",
  "earthquakes_path": "<passthrough>",
  "plate_code": "<two-letter PB2002 code, uppercase>",
  "extremum": "furthest" | "closest",
  "top_n": <positive integer>
}}
```

### `plate_code` — PB2002 two-letter codes

Map the plate the user names to its PB2002 code. If the user already gave a
two-letter code, uppercase it and use it. If no plate is identified at all,
default to `"PA"` (Pacific) — the canonical example in this domain.

| Plate (any surface form)             | Code |
|--------------------------------------|------|
| Pacific                              | PA   |
| North American / North America       | NA   |
| South American / South America       | SA   |
| Eurasian / Eurasia                   | EU   |
| African / Africa                     | AF   |
| Indian / India                       | IN   |
| Australian / Australia               | AU   |
| Antarctic / Antarctica               | AN   |
| Nazca                                | NZ   |
| Juan de Fuca                         | JF   |
| Cocos                                | CO   |
| Caribbean                            | CA   |
| Arabian / Arabia                     | AR   |
| Philippine Sea / Philippine          | PS   |
| Scotia                               | SC   |
| Okhotsk                              | OK   |

Any other named PB2002 plate: use its standard two-letter code (e.g. Sunda =
SU, Yangtze = YA, Amur = AM, Somalia = SO). If the user names something that
is not a tectonic plate, still default to `"PA"` and keep going — the script
will raise a clear error listing the available plate identifiers if the code
is wrong.

### `extremum`

- `"closest"` when the user asks about the earthquake nearest to the plate
  boundary (keywords: nearest, closest, near, shortest distance).
- `"furthest"` otherwise, including the common "most interior",
  "deepest inside", "furthest from any boundary", or when the user does not
  specify. This is the canonical question.

### `top_n`

- `1` by default and whenever the user asks for "the" earthquake.
- Otherwise, the integer the user names ("top 5", "three furthest", etc.).

## Output

Return the JSON object only. No surrounding prose, no code fences.
