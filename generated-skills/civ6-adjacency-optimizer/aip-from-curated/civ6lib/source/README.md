# civ6lib — AIP Conversion Notes

## Source

Converted from `vendor/skillsbench/tasks/civ6-adjacency-optimizer/environment/skills/civ6lib/SKILL.md` (curated freeform Agent Skill) into AIP format.

## Schema choice

Used `procedure.schema.json` (the available AIP schema). civ6lib is primarily a domain reference library — the procedural shape is light (a 7-step validation checklist plus a usage pattern), with most content being rule tables. The procedure schema's optional `scenarios`, `decisions`, and `anti_patterns` fields plus progressive disclosure to `references/` carry the reference content without inventing a new schema.

## Content map

| Source content | AIP body location | Notes |
|---|---|---|
| Module list (placement_rules, adjacency_rules) | `purpose`, `steps`, `references/key-classes.md` | Mapped |
| Python usage example | `scenarios[0]` + `references/key-classes.md` | Mapped |
| City Placement Rules tables | `references/placement-rules.md` | Mapped (moved to references for progressive disclosure) |
| District Placement universal/specific rules | `references/placement-rules.md` | Mapped |
| District limit population formula + table | `references/placement-rules.md` | Mapped |
| Non-specialty districts list | `references/placement-rules.md` | Mapped |
| Uniqueness rules table | `references/placement-rules.md` | Mapped |
| Critical Rule: Minor Bonus Calculation | `anti_patterns[0]`, `decisions`, `references/adjacency-rules.md` | Mapped (emphasized in body, full example in references) |
| Adjacency rules per district (Campus, Holy Site, etc.) | `references/adjacency-rules.md` | Mapped |
| Districts with NO adjacency bonuses list | `references/adjacency-rules.md` | Mapped |
| Government Plaza adjacency bonus | `references/adjacency-rules.md` | Mapped |
| Districts that count for "+0.5 per District" list | `references/adjacency-rules.md` | Mapped |
| Destruction effects | `anti_patterns`, `references/placement-rules.md` | Mapped |
| Key Classes section | `references/key-classes.md` | Mapped |
| Quick Validation Checklist (7 items) | `steps` | Mapped (one-to-one) |

## Deliberate drops

None — all source content is preserved either in the SKILL.md body or in `references/`.

## Frontmatter

- `name` is preserved as `civ6lib` (mandatory — the task's mounted skill must match this exact name).
- `description` is preserved verbatim from source.
