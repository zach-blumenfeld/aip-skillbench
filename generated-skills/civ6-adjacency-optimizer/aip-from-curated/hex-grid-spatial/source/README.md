# AIP Conversion Notes — hex-grid-spatial

## Source

- Original SKILL.md: `source/SKILL.original.md` (verbatim copy from
  `vendor/skillsbench/tasks/civ6-adjacency-optimizer/environment/skills/hex-grid-spatial/SKILL.md`).
- Original script: `vendor/.../scripts/hex_utils.py` (copied verbatim to
  `scripts/hex_utils.py`).

## Schema choice

Selected `procedure.schema.json` (procedure-style AIP). The skill exposes a
small library of pure hex-math functions that an agent invokes selectively. The
procedure schema's script-backed `steps` cleanly model "callable operations" —
each function becomes a node with declared `inputs`/`outputs` pointing at
`scripts/hex_utils.py`. Steps are independent (no `depends_on`); the agent
picks the operation it needs.

No new schema was drafted — reuse satisfies the spec.

## Script choices (per AIP best practices)

The hex-math operations are textbook deterministic logic over integer inputs —
exactly the case the AIP best practices say to script:

- numeric calculations (cube-coordinate distance)
- lookup tables (odd-row vs even-row direction offsets)
- fixed if/then over structured input (even vs odd row branch)

So every operation is script-backed. The single `scripts/hex_utils.py` module
holds them all (favoring "fewer script files for simplicity"). The original
implementation is already lean and uses only the Python stdlib — no library
substitution needed.

## Source-to-body mapping

| Source content                              | Destination                              |
|---------------------------------------------|------------------------------------------|
| Header / coordinate-system prose            | `purpose` + opening of `scenarios`       |
| Direction index diagram                     | `anti_patterns` (avoid wrong indexing) + script docstrings |
| `get_neighbors` function + example          | step `get-neighbors` (script-backed)     |
| `hex_distance` function + example           | step `hex-distance` (script-backed)      |
| `get_tiles_in_range` function + example     | step `tiles-in-range` (script-backed)    |
| `get_neighbor_at_direction` (script only)   | step `neighbor-at-direction`             |
| `get_direction_to_neighbor` (script only)   | step `direction-to-neighbor`             |
| `is_adjacent` (script only)                 | step `is-adjacent`                       |
| `get_opposite_direction` (script only)      | step `opposite-direction`                |
| Even-vs-odd row diagonal table              | `anti_patterns` (don't share offsets)    |
| Usage examples block                        | `scenarios`                              |

The script exports a few helper functions (`is_adjacent`,
`get_neighbor_at_direction`, etc.) that the source SKILL.md does not document
in prose. They're real public functions in `hex_utils.py`, so they're surfaced
as steps in the AIP body — recovering knowledge the agent would otherwise miss.

## Deliberate drops

None. All source prose either maps to a typed field or is preserved verbatim
inside `scripts/hex_utils.py` (which the agent loads when running a step).
