# Source — flight-plan-parser (AIP conversion)

## What this skill is

Converts natural-language flight commands (the four shapes the drone
simulator accepts) into the `(waypoints, waypoint_times, modes)` triple that
`trajectory_planner` and `main.py` consume.

## Provenance

Adapted from
`vendor/skillsbench/tasks/drone-planning-control/environment/skills/flight-plan-parser/SKILL.md`
(see `ORIGINAL_SKILL.md` in this directory). The original is freeform prose
describing the regex strategy, state machine, and output shapes; this AIP
version preserves the same content but moves the parser logic into a
script-backed step graph so the agent can drop a working module into the
project rather than re-deriving it.

## Schema choice

- `procedure.schema.json` (procedure category) — the original is a workflow:
  ingest commands → parse → emit structured output. No new schema required.

## Source → AIP mapping

| Original SKILL.md content                                  | AIP location                                        |
| ---------------------------------------------------------- | --------------------------------------------------- |
| Overview / output format                                   | `purpose`, `references/command-grammar.md`          |
| Supported commands table                                   | `references/command-grammar.md`                     |
| Implementation logic (stateful parser, ensure-start, etc.) | `scripts/flight_plan_parser.py`                     |
| Regex strategy (case-insensitive, capture groups)          | `scripts/flight_plan_parser.py` + grammar reference |
| Key design rules (auto-start waypoint, copy lists)         | `scripts/flight_plan_parser.py` + grammar reference |
| Usage snippet (single-command example)                     | `scenarios` in `SKILL.md` + grammar reference       |

## Notable corrections / additions vs. the original

The original SKILL.md says *"Auto-insert a starting waypoint at (0, 0, 0,
t=0) on the first command if the list is empty."* That is true for the
`takeoff` handler but not the full story:

- `hover` snaps `_pos.z = h` **before** inserting the start waypoint, so a
  leading hover starts at z=h, not z=0.
- `land` snaps `_pos.z = h` similarly so the descent starts at the stated
  altitude.
- `fly` seeds the start from its `from (...)` triple, overriding the default
  origin.

The reference implementation in the canonical oracle solution
(`tasks/drone-planning-control/solution/solve.sh`) shows the precise per-mode
ordering. The script bundled here mirrors that ordering exactly; the grammar
reference documents it explicitly so it is no longer load-bearing on prose.

The `Fly` regex also tolerates an optional `location` keyword between the
`from (...)` and `to (...)` clauses (matching the oracle behaviour), which
the original SKILL.md did not document.

## Deliberate drops

None. Every line of the original is either captured in the SKILL.md body, a
scenario, the grammar reference, or the script.
