# Source notes: pacific-plate-earthquake-distance

This AIP skill was authored from a single task instruction:
`vendor/skillsbench/tasks/earthquake-plate-calculation/instruction.md`.

## Source-to-skill mapping

| Source item                                                     | Where it landed                                |
|-----------------------------------------------------------------|------------------------------------------------|
| "Find the earthquake furthest from the Pacific plate boundary"  | `purpose`, `trigger_when`, `steps[run-solver]` |
| "within the Pacific plate itself"                               | within-polygon filter in `scripts/solve.py`    |
| "Use GeoPandas projections"                                     | Pacific-centered AEQD, `solve.py`              |
| Output schema (id, place, time, mag, lat, lon, distance_km)     | `scripts/solve.py` writer + `verify-answer`    |
| time as ISO 8601 `YYYY-MM-DDTHH:MM:SSZ`                         | `ms_to_iso8601()` in `solve.py`                |
| `distance_km` rounded to 2 decimals                             | `round(..., 2)` in `solve.py`                  |
| `/root/earthquakes_2024.json`                                   | default `--earthquakes` flag                   |
| `/root/PB2002_boundaries.json`                                  | default `--boundaries` flag                    |
| `/root/PB2002_plates.json`                                      | default `--plates` flag                        |
| Output `/root/answer.json`                                      | default `--output` flag                        |

## Decisions

- **Schema reuse.** This is a procedural pipeline (load → filter → project →
  measure → write), so it reuses the bundled `procedure.schema.json` from the
  AIP spec rather than introducing a new schema.
- **Single-script implementation.** All numeric/geospatial logic lives in
  `scripts/solve.py`. The SKILL.md body lays out the pipeline as steps for
  readability, but the actual execution is one `solve.py` invocation —
  consistent with AIP's "scripts are the source of truth for logic" guidance.
- **Projection choice.** Azimuthal Equidistant centred at (0°, −160°). The
  Pacific plate spans the antimeridian, so anything centred near 0° longitude
  (default Web Mercator, EPSG:3857, etc.) shatters the polygon. AEQD at
  −160° puts the seam through Africa, leaving the Pacific contiguous.
- **Boundary source.** Prefers PB2002 boundary lines filtered to PA-adjacent
  segments; falls back to the Pacific polygon's own `.boundary` if attribute
  filtering fails. Both are mathematically equivalent for points inside the
  Pacific (the nearest plate-boundary point is necessarily on the Pacific's
  own boundary, by topology).

## Deliberate drops

- No "alternative projections" section. The instruction explicitly asks for
  GeoPandas projections; a single, well-chosen projection is more useful than
  a menu (per AIP best practices: "Provide defaults, not menus").
- No general earthquake-analysis background. The agent already knows what an
  earthquake catalog is — the skill only adds project-specific facts
  (PB2002 codes, USGS field shapes, antimeridian handling).
