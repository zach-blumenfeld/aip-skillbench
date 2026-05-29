# Source notes — dialogue_graph AIP skill

## Provenance

Adapted from the curated Agent Skill at
`vendor/skillsbench/tasks/dialogue-parser/environment/skills/dialogue_graph/`
(see `original-SKILL.md`). The original is a freeform-markdown reference for a
`dialogue_graph` Python library that builds, validates, visualizes, and
serializes dialogue trees. This AIP version preserves the library verbatim and
adds a deterministic parser script so an agent can solve the bundled
dialogue-parser task end-to-end without rewriting the format rules.

## Schema choice

Uses `procedure.schema.json` (v0.3a3, bundled in this `source/`). The
dialogue-parser task is a small DAG of work — read script, parse, validate,
serialize JSON, render DOT — which is exactly what the procedure schema is
designed to describe. No new schema is needed.

## Script vs prose decisions

The procedure has two natural parts:

1. **Parsing the bracketed script format** — fully deterministic if/else over
   regex-classified lines (`[Header]`, `Speaker: Text -> Target`,
   `N. Choice -> Target`). Scripted in `scripts/parse_script.py`. Putting this
   in prose would let two agents produce subtly different graphs on the same
   input (different whitespace handling, different treatment of `[Skill]`
   tags, different decisions about empty `text` on transition edges).
2. **DOT/JSON serialization** — handled by the library's existing `to_json()`
   and `visualize(format="dot")` methods. The parser script delegates to them.

The library itself (`scripts/dialogue_graph.py`) is copied verbatim from the
source skill; we do not redefine `Node`, `Edge`, `Graph` in the parser.

Validation of the parsed graph (missing edge targets, etc.) is a one-line call
to `graph.validate()` inside the parser script. Surfacing the warnings to the
agent is a prose step — judging *what* to do with warnings (re-parse,
escalate, accept) is contextual and shouldn't be hard-coded.

## Frontmatter `name` note

The original SKILL.md declares `name: dialogue-graph` (hyphenated) while the
parent directory is `dialogue_graph` (underscored). The Agent Skills spec and
the AIP validator both require `name` to match the folder name. The task brief
explicitly forbids changing the `name:` field because the task's mounted skill
must match. We therefore keep `name: dialogue-graph` and accept that
`scripts/validate.py` will flag a `name_mismatch` error on this skill — it is
the intended behavior under the task constraint, not a defect to fix.

## File layout

```
dialogue_graph/
├── SKILL.md                       # AIP frontmatter + fenced YAML body
├── source/
│   ├── procedure.schema.json      # Bundled AIP schema (v0.3a3)
│   ├── original-SKILL.md          # Verbatim copy of the curated skill
│   └── README.md                  # This file
└── scripts/
    ├── dialogue_graph.py          # Verbatim copy of the library
    └── parse_script.py            # Deterministic script.txt parser + serializer
```

## Coverage check against `original-SKILL.md`

Every API surface in the original is captured here:

| Original section            | Where it lives now                                          |
|-----------------------------|-------------------------------------------------------------|
| `Graph()` constructor       | Library `scripts/dialogue_graph.py` (verbatim)              |
| `add_node`, `add_edge`      | Library + `parse_script.py` uses both                       |
| `to_dict`, `to_json`        | Library + `parse_script.py` writes JSON via `to_json`       |
| `validate`                  | Library + `parse_script.py` calls and reports warnings      |
| `visualize` (PNG/SVG/DOT)   | Library + `parse_script.py` calls with `format="dot"`       |
| Skill-check edge styling    | Library `visualize` (bold-blue when `[Skill]` is in label)  |
| `from_file`/`from_dict`/`from_json` | Library — exposed for agents loading an existing graph |
| When-to-use list (parser/editor/game-logic/viz) | `trigger_when` block in SKILL.md       |
