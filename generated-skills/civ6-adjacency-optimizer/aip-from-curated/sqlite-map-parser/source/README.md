# sqlite-map-parser — AIP authoring notes

This skill is the AIP-format port of the curated Agent Skill at
`vendor/skillsbench/tasks/civ6-adjacency-optimizer/environment/skills/sqlite-map-parser/`.
The original `SKILL.md` is kept verbatim in `source/SOURCE-SKILL.md` for
diff-checking.

## Schema choice

Uses `procedure.schema.json` (bundled here in `source/`). The source skill
is a 4-step procedure (explore → understand relationships → extract →
output) — exactly what the Procedure schema covers. No need to draft a new
schema.

## Step decomposition

The original prose collapses to **five** explicit nodes:

| AIP step | Original section | Backed by |
|----------|------------------|-----------|
| `explore-schema` | Step 1 (Schema introspection PRAGMAs) + Step 2 FK identification | `scripts/explore_schema.py` |
| `identify-key-tables` | Step 2 *interpretation* (which table is main, which is overlay) | prose |
| `plan-extraction` | Step 3 *planning* + Step 4 output-shape choice | prose, `one_of` for dict vs array |
| `extract-and-transform` | Step 3 Python template | prose, reference template in `references/extraction-patterns.md` |
| `validate-output` | (new) implicit in the source's "build indexed data structure" | prose |

`validate-output` is a deliberate addition: the source skill assumes the
parse succeeded but never instructs the agent to check it. A short
self-validation step catches the common failures (wrong join key, off-by-
one on linear-index decomposition, schema-variant overlays silently dropped).

## Script vs prose calls

- **Script — explore-schema.** Schema introspection is deterministic: same
  database in, same JSON out. Replaces six different SQL PRAGMAs with one
  call. Eliminates the "did the agent remember to also check indexes?"
  failure mode.
- **Prose — identify-key-tables, plan-extraction, extract-and-transform,
  validate-output.** Each hinges on interpreting the schema dump: which
  table is the metadata table, which join column maps to which output
  field, whether the output should be a dict or an array. AIP's guidance:
  *don't script a step whose decision logic depends on judging the input
  data.*

## Content drops (deliberate)

Nothing material from the source skill was dropped. The Python parse
template moved to `references/extraction-patterns.md` (progressive
disclosure — only loads when the extract step runs). The common-schema-
pattern catalog and SQL-debugging cheat sheet moved to
`references/common-patterns.md` for the same reason. Both are referenced
by name from the relevant prose step so the agent knows when to load them.

## Files

```
sqlite-map-parser/
├── SKILL.md                              # AIP frontmatter + YAML body
├── scripts/
│   └── explore_schema.py                 # stdlib-only schema dumper
├── references/
│   ├── extraction-patterns.md            # Python parse template
│   └── common-patterns.md                # schema archetypes + debug SQL
└── source/
    ├── procedure.schema.json             # bundled AIP schema
    ├── SOURCE-SKILL.md                   # original curated SKILL.md
    └── README.md                         # this file
```
