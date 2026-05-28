# Source materials — sqlite-map-parser (AIP conversion)

This folder contains the inputs used to author the AIP version of
`sqlite-map-parser`.

## Files

- `SKILL.md` — the original curated freeform-markdown skill, copied
  verbatim from
  `vendor/skillsbench/tasks/civ6-adjacency-optimizer/environment/skills/sqlite-map-parser/SKILL.md`.
  This is the canonical content the AIP `SKILL.md` is compiled from.
- `procedure.schema.json` — the AIP `procedure` schema this skill
  validates against. Bundled so the skill is self-contained.

## Compilation logic

The original is a four-step procedure (Explore schema → Understand
relationships → Extract/transform → Output JSON) interleaved with SQL
and Python snippets, common schema patterns, and debugging queries.
The `procedure` schema fits cleanly:

| Source content                          | AIP field                          |
|-----------------------------------------|------------------------------------|
| Top-level intent                         | `purpose`                          |
| "Use when …" cues from `description`     | `trigger_when`                     |
| Step 1 — Explore the Schema              | `steps[0]` (`explore-schema`)      |
| Step 2 — Understand Relationships        | `steps[1]` (`understand-relationships`) |
| Step 3 — Extract and Transform           | `steps[2]` (`extract-transform`)   |
| Step 4 — Output as Structured JSON       | `steps[3]` (`output-json`)         |
| Map vs Array output guidance             | `decisions`                        |
| Common Schema Patterns (grid, hierarchy, enum) | `scenarios`                  |
| Debugging Tips SQL snippets              | `search_shortcuts`                 |

All SQL and Python snippets from the original are preserved inside the
relevant step descriptions as fenced code blocks. No content was
intentionally dropped.

## Constraints honored

- `name: sqlite-map-parser` is preserved unchanged — the task's mounted
  skill name must match the original.
- The bundled `procedure.schema.json` is byte-identical to the canonical
  schema referenced by `metadata.aip.schemaId`.
