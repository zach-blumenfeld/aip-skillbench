# civ6-adjacency-optimizer — design notes

## Source

Authored from a single source: the task instruction at
`vendor/skillsbench/tasks/civ6-adjacency-optimizer/instruction.md`.

The task asks the agent to act as an optimizer for Civilization VI
district adjacency bonuses. The agent receives a scenario JSON and a
.Civ6Map binary, must choose city-center(s) and districts, place them
validly, and report the total adjacency bonus.

## Scope of the skill

The skill encodes the procedural knowledge an agent needs to:

1. Read the scenario and parse the .Civ6Map (SQLite-backed) terrain grid.
2. Apply Civ6 hex adjacency to compute per-district bonuses.
3. Pick city centers and districts greedily under terrain and
   population constraints.
4. Validate the solution before writing it, so an invalid placement
   doesn't zero out the score.

## Schema choice

The procedure has clear sequenced steps with conditional branching
(single-city vs multi-city, civ-specific districts) and a decision
table (when to fall back to brute-force search). That matches the
`procedure.schema.json` shape (steps, decisions, anti_patterns,
scenarios). Reusing the existing schema, not authoring a new one.

## Body shape rationale (selective typing)

- `steps` — full typed records (`name`, `description`, `depends_on`).
  An agent / governance query may want to look up step-by-name.
- `decisions` — full records. Each row is a `signal -> action` lookup.
- `trigger_when`, `anti_patterns` — flat string lists. Plural,
  one-line items, nothing to filter on.
- `purpose`, `scope_and_approval` — singular `|`-blocks. Nothing
  iterates them.
- `scenarios` — typed records to enumerate worked cases.
- No `modes` / `search_shortcuts` / `integrations` blocks — the
  procedure doesn't have meaningful sub-modes or external partners.

## Resource layout

- `scripts/` — runnable Python utilities. Together they form a
  pipeline: `inspect_map → parse_map → solve → validate_solution`.
  `compute_adjacency` and `hex_utils` are library helpers.
- `references/` — domain knowledge the agent only needs when actually
  computing adjacency or parsing the map. Progressive disclosure: the
  body points at these by name when the relevant step runs.

## Known gaps / agent-time verification

- The exact adjacency formula the grader uses is not given in the
  instruction. The skill encodes the base-game vanilla rules and tells
  the agent to verify against any oracle / scoring code visible in the
  environment.
- The hex layout (odd-r vs even-r) is not specified by the
  instruction. `hex_utils.py` defaults to odd-r and the skill body
  tells the agent to verify against known-adjacent pairs before
  trusting it.
- River-edge encoding varies across Civ6 map versions; the parser
  reads both `Plots.River*` columns and a `Rivers` edge table when
  present.
