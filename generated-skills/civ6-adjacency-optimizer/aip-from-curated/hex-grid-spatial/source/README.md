# hex-grid-spatial — AIP authoring notes

## Source

Converted from `vendor/skillsbench/tasks/civ6-adjacency-optimizer/environment/skills/hex-grid-spatial/`:

- `SOURCE-SKILL.md` — original freeform `SKILL.md` (renamed to avoid clashing with the AIP `SKILL.md` at the skill root).
- `procedure.schema.json` — bundled AIP schema this skill validates against.

## Schema choice

Reused `procedure.schema.json` rather than authoring a new schema. The skill is a thin library of pure hex-math functions; modeled here as a procedure whose single step routes the agent to the correct function via `one_of`, with `scripts/hex_utils.py` as the script of record. All conditional logic (even-row vs odd-row offset, cube-coord conversion) lives in the script — the YAML body lists operations, not formulas.

## Completeness mapping

Every source item is captured. Line-by-line classification of `SOURCE-SKILL.md`:

| Source content | Classification | Location |
|---|---|---|
| Coordinate system (odd-r, tile 0 bottom-left, axes) | Mapped | `purpose`; full detail in `scripts/hex_utils.py` module docstring + comments |
| Direction indices diagram (0=E … 5=SE) | Mapped | Documented in `scripts/hex_utils.py` direction constants |
| `get_neighbors` function body | Mapped | `scripts/hex_utils.py` (verbatim) |
| `hex_distance` function body | Mapped | `scripts/hex_utils.py` (verbatim) |
| `get_tiles_in_range` function body | Mapped | `scripts/hex_utils.py` (verbatim) |
| Usage examples | Mapped | `scenarios` |
| Even vs odd row direction table | Mapped | `DIRECTIONS_EVEN_ROW` / `DIRECTIONS_ODD_ROW` constants in script |
| East/West always (±1, 0) note | Mapped | Direction constants in script; `anti_patterns` warns against re-deriving |

The script also extends the source SKILL with `get_neighbor_at_direction`, `get_direction_to_neighbor`, `is_adjacent`, and `get_opposite_direction` — these were already in the curated script and are surfaced in the body's `one_of` so the agent uses them instead of re-deriving.

## Notes

- `name:` is preserved verbatim (`hex-grid-spatial`) — the task harness mounts the skill by this exact name.
- Read-only utility: no mutation, no I/O, no approval gate. `scope_and_approval` reflects that.
