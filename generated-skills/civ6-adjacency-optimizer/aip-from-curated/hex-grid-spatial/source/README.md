# Source notes: hex-grid-spatial → AIP

## Origin

Curated Agent Skill from
`vendor/skillsbench/tasks/civ6-adjacency-optimizer/environment/skills/hex-grid-spatial/`.
Original `SKILL.md` and `scripts/hex_utils.py` are preserved verbatim — the
former in `source/SKILL.md`, the latter at the skill root in `scripts/`.

## Schema choice

Reused `procedure.schema.json` (no new schema drafted). The skill is a small
library of hex-grid math helpers, but the agent-facing content fits cleanly
into a procedure shape:

- `purpose` carries the coordinate system contract (odd-r offset).
- `trigger_when` carries activation conditions.
- `steps` cover the workflow of using the utilities (import, pick the right
  function, account for row parity).
- `decisions` map "what I need" → "which helper to call".
- `scenarios` carry the worked examples from the original `SKILL.md`.
- `anti_patterns` warn about even/odd row diagonal direction differences,
  which is the most common source of bugs.

## Compilation classification

Walking the source `SKILL.md` line-by-line:

- **Coordinate system** description (odd-r, tile 0 origin, x/y axes) →
  Mapped to `purpose`.
- **Direction indices** ASCII diagram and 0=E..5=SE legend → Mapped to
  `purpose` (compressed) and the `select-direction-or-helper` step.
- **`get_neighbors` function + signature** → Mapped to a `decisions` row
  and a `scenarios` row. Full implementation lives in
  `scripts/hex_utils.py`.
- **`hex_distance` function** → Mapped to a `decisions` row and a
  `scenarios` row.
- **`get_tiles_in_range` function** → Mapped to a `decisions` row and a
  `scenarios` row.
- **Usage examples** (neighbors of (21,13), distance, adjacency, workable
  tiles) → Mapped to `scenarios`.
- **Even vs odd row table** → Mapped to `anti_patterns` (the key trap)
  and surfaced in the `account-for-row-parity` step. The literal
  direction table itself isn't reproduced in the body — agents read
  `scripts/hex_utils.py` for the canonical offsets (`DIRECTIONS_EVEN_ROW`
  / `DIRECTIONS_ODD_ROW`).

Deliberate drops:

- The literal Python source blocks from the original `SKILL.md` are not
  re-embedded in the AIP body. Rationale: `scripts/hex_utils.py` is the
  canonical implementation and is bundled alongside; duplicating code in
  the body would bloat tokens and risk drift. The body points to the
  script instead.
