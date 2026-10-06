# Parse the user's earthquake/plate request

You are turning a free-form user request into the parameters the compute
step needs. Return your answer as a JSON object with these keys:

- `plate_code` (string): the two-letter PB2002 plate code to analyze
  (e.g., `PA` Pacific, `NA` North America, `SA` South America, `EU`
  Eurasia, `AF` Africa, `AN` Antarctica, `AU` Australia, `IN` India,
  `NZ` Nazca, `JF` Juan de Fuca, `PH` Philippine, `CO` Cocos, `CA`
  Caribbean, `AR` Arabia, `SO` Somalia, `SC` Scotia). Look up the code
  in `references/pb2002-plate-codes.md` if the user names a plate instead.
- `metric` (string, one of `furthest`, `nearest`, `mean`, `median`):
  what statistic to compute over the per-earthquake distances. Map:
  - "farthest / furthest / deepest-interior / most interior" → `furthest`
  - "closest / nearest / shortest" → `nearest`
  - "average / mean" → `mean`
  - "median / typical" → `median`
  Default to `furthest` if the user did not say.
- `boundary_scope` (string, one of `plate`, `all`): which plate
  boundary segments count as "the boundary." Default to `plate` — only
  boundary segments that touch the target plate (where `PlateA` or
  `PlateB` equals `plate_code`). Use `all` only if the user explicitly
  asks for distance to any plate boundary on Earth.

## User request

{user_request}

## Known inputs

- Earthquakes GeoJSON: `{earthquakes_path}`
- Plates GeoJSON: `{plates_path}`
- Boundaries GeoJSON: `{boundaries_path}`

Return only the JSON object. No prose, no code fence.
