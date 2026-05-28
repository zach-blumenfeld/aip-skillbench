# Source materials — `power-flow-data` AIP conversion

This directory bundles the materials used to compile the AIP-format
`SKILL.md` at the skill root.

## Files

- `procedure.schema.json` — the AIP schema this skill validates against
  (`$id: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json`).
  Bundled locally so the skill is self-contained.
- `original-SKILL.md` — the curated skill body provided by the user as
  the canonical human-readable source, copied verbatim from
  `vendor/skillsbench/tasks/energy-market-pricing/environment/skills/power-flow-data/SKILL.md`.

## Conversion logic

The original skill is a reference/recipe guide for parsing MATPOWER-format
power-system network data (PGLib-OPF benchmark library). Its content is a
mix of:

1. A warning about how to open large network JSON files (use Python's
   parser; do not stream line-by-line).
2. A short sequence of recipes — load, summarize, convert to numpy, build
   a bus-number→index mapping, identify topology, interpret branches,
   compute total load.
3. Reference tables for bus types, per-unit conventions, and reserve
   fields.

The procedure schema is a good fit because the actionable recipes form
a natural ordered procedure. Mapping decisions:

| Source section | AIP body field |
|---|---|
| Warning about large files + `wc -l` / `du -h` check | First `step` (`open-network-with-python`) and an `anti_patterns` entry |
| Quick summary print | `step: print-summary` |
| `load_network` helper | `step: load-into-numpy` |
| Reserve data fields | `search_shortcuts.Reserve Data` (it is reference content, surfaced when the agent needs it) |
| Bus number mapping | `step: build-bus-number-mapping` |
| `get_generators_at_bus` / `find_slack_bus` | `step: identify-topology` |
| `get_branch_info` | `step: interpret-branches` |
| `total_load` | `step: compute-total-load` |
| Bus type table | `search_shortcuts.Bus Types` |
| Per-unit system | `search_shortcuts.Per-Unit System` |
| MATPOWER / PGLib-OPF origin note | `search_shortcuts.Data Source` |
| "Never read line-by-line" warning | `anti_patterns` entry |
| "Type 3 is slack, not type 1" (implicit in table) | `anti_patterns` entry |

Reference tables and the per-unit conversion block are grouped under
`search_shortcuts` because they are lookup-style content the agent
consults during execution rather than a sequential action.

The `name` field (`power-flow-data`) is preserved exactly so the
mounted-skill name in the task harness still matches.

## Deliberate drops

None. Every distinct line of `original-SKILL.md` is either mapped to
a body field above or, for the inline code blocks, embedded inside the
relevant step description.
