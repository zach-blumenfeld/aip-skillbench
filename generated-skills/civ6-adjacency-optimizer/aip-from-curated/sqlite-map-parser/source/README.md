# sqlite-map-parser — AIP conversion notes

## Source

- Original SKILL.md: `SKILL.original.md` — curated freeform-markdown skill
  authored for the Civ6 Adjacency Optimizer task. Teaches a 4-step procedure:
  explore schema → understand relationships → extract & transform → output
  as JSON, with common-pattern callouts (grid/hierarchical/enum) and a
  debugging cheat sheet.

## Target

- AIP `procedure` schema (`procedure.schema.json`, $id pinned to
  `aip v0.3a2`). The original is a workflow of script-shaped steps with
  inputs/outputs — natural fit.

## Conversion logic

The original mixes prescriptive SQL/Python snippets with reasoning steps.
The AIP version splits the two:

- **Deterministic logic → `scripts/`.** Schema introspection
  (`sqlite_master`, `PRAGMA table_info/index_list/foreign_key_list`),
  table extraction with optional joins/lookups, and diagnostic queries
  are coded once so the agent doesn't reinvent them. This is the AIP
  best-practice for "domain-specific logic + numeric calculations
  (linear-id → x,y)".
- **Reasoning → step prose.** Choosing the main entity, deciding key
  shape (id vs x,y), picking output container (map vs array) stays as
  agent judgment, with a `one_of` for the container decision.
- **Civ6-specific cues** (linear-ID → coordinate math, metadata table
  width/height) are preserved as scenarios + step descriptions.

## Source-to-body mapping (completeness check)

| Source content                                        | AIP location                                              |
|-------------------------------------------------------|-----------------------------------------------------------|
| Step 1: list tables, PRAGMA table_info / index_list / index_info | `steps.explore-schema` (via `scripts/explore_schema.py`)  |
| Step 2: foreign_key_list, ID-based joins              | `steps.explore-schema` output + `steps.identify-relationships` prose |
| Step 2: linear-id → (x, y) coordinate math            | `steps.identify-relationships` description + `scripts/extract_to_json.py` (`key_kind: xy`) |
| Step 3: Python parse_sqlite_to_json template          | `scripts/extract_to_json.py` (config-driven)              |
| Step 3: `safe_query` (handle missing tables)          | `scripts/explore_schema.py` + `extract_to_json.py` use the same defensive pattern |
| Step 4: Map vs Array output shape                     | `steps.choose-output-shape` (`one_of`) + `--shape` flag on `extract_to_json.py` |
| Common patterns: Grid/Map data                        | `references/common-patterns.md` + `scenarios[0]`          |
| Common patterns: Hierarchical                         | `references/common-patterns.md`                           |
| Common patterns: Enum/Lookup                          | `references/common-patterns.md` + `extract_to_json.py` `lookups` field |
| Debugging tips (sample, count, distinct, null)        | `scripts/sample_table.py` + `steps.spot-check`            |
| (none in source) Linear ID may be 1-indexed; verify   | Added to `anti_patterns` — the agent will hit this        |

No deliberate drops — every snippet is either mapped or expanded.

## Why scripts not prose

The original SKILL.md embeds verbatim SQL and Python templates the agent
is expected to copy. Copying invites drift (typos, missed PRAGMAs, wrong
quoting on weird table names). Encoding them once in
`scripts/explore_schema.py` and `scripts/extract_to_json.py` removes that
class of mistake and lets the agent focus on the reasoning steps.
