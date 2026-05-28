# Source notes — earthquake-plate-boundary-distance

This skill was authored from the task instruction at
`vendor/skillsbench/tasks/earthquake-plate-calculation/instruction.md`. No
pre-existing skill or solution was consulted.

## Scope captured

The instruction asks for: the earthquake furthest from the Pacific plate
boundary, restricted to earthquakes inside the Pacific plate, computed with
GeoPandas projections, output to `/root/answer.json` with seven specified
fields.

The skill encodes the **reusable procedure** for any plate-interior-furthest-
from-boundary question (default Pacific, but `solve.py --plate` accepts any
PB2002 plate name or two-letter code). Pacific-specific gotchas
(antimeridian, projection choice) live in `references/projections.md` so the
SKILL.md body stays lean.

## Schema

Uses the bundled `procedure.schema.json` (the AIP procedure schema). This task
is a linear pipeline with one conditional (which CRS), which fits the
procedure shape directly — no new schema needed.

## Mapping check

| Instruction element                                  | Where it lands |
|------------------------------------------------------|----------------|
| "find the earthquake furthest from the Pacific plate boundary within the Pacific plate" | `purpose`, `trigger_when`, `steps.identify-plate`, `steps.filter-to-plate-interior`, `steps.measure-distance` |
| "Use GeoPandas projections"                          | `steps.choose-projected-crs`, `decisions`, `references/projections.md` |
| Output to `/root/answer.json`                        | `steps.emit-answer`, `references/data-formats.md` |
| Required output fields (id/place/time/magnitude/lat/lon/distance_km) | `steps.emit-answer`, `references/data-formats.md`, `scripts/solve.py` |
| `time` ISO 8601 (`YYYY-MM-DDTHH:MM:SSZ`)             | `steps.emit-answer` field-formatting note, `solve.py::epoch_ms_to_iso8601_z` |
| `distance_km` rounded to 2 dp                        | `steps.emit-answer`, `solve.py` |
| Input file paths (`/root/earthquakes_2024.json`, etc.) | `solve.py` defaults, `references/data-formats.md` |

No deliberate drops.
