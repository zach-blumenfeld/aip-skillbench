# AIP conversion notes — `trl` reference skill

## Intent

The source skill at
`vendor/skillsbench/tasks/debug-trl-grpo/environment/skills/trl/SKILL.md`
is a *library reference*: it documents the TRL (Transformer
Reinforcement Learning) codebase layout, trainer hierarchy, shared
utility contracts, and configuration system, and instructs the agent
to load it before reading or editing anything under `trl/`.

## Schema choice

Only `procedure.schema.json` is bundled with the AIP skill, and the
brief was to convert this to AIP without drafting new schemas.
Procedure fits with a small reframe: the skill is treated as a
**lookup procedure** the agent runs immediately before touching TRL
code (identify target file → locate in package structure → confirm
parent class / overridden methods → review shared-utility contracts →
check config fields → load detailed reference if needed). All
substantive reference content (trainer table, utility contracts,
config table, available references table) lives in `search_shortcuts`
where the typed `category` label keeps the lookup queryable while
the body retains the original prose / tables.

## Content mapping (source → AIP body)

| Source section | AIP field |
|---|---|
| Package Structure tree | `search_shortcuts[category=package-structure].body` |
| Trainer Hierarchy diagram + override note | `search_shortcuts[category=trainer-hierarchy].body` |
| `selective_log_softmax` contract | `search_shortcuts[category=utility-contracts].body` |
| `decode_and_strip_padding` contract | `search_shortcuts[category=utility-contracts].body` |
| `pad` / `pad_to_length` note | `search_shortcuts[category=utility-contracts].body` |
| Configuration System table | `search_shortcuts[category=configs].body` |
| Available References table | `search_shortcuts[category=references].body` |
| "Use proactively before reading or editing any file under `trl/`" | `trigger_when` |
| "Read the source before modifying; contracts are what callers rely on" | `anti_patterns` |

## Files preserved verbatim

- `references/trl-codebase.md` — copied verbatim from the source.
  Referenced by `search_shortcuts[category=references]` and by the
  `load-detailed-reference` step.

## Frontmatter

- `name: trl` — kept unchanged per task brief; must match the
  parent directory name so the skillbench task can mount this skill
  at the expected path.
- `description` — kept close to the original so the activation
  signal an agent sees at startup is unchanged.
