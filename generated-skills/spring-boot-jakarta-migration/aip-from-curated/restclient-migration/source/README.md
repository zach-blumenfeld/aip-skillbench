# Source — restclient-migration AIP skill

## Origin

Converted verbatim-in-intent from the curated Agent Skill at:

```
vendor/skillsbench/tasks/spring-boot-jakarta-migration/environment/skills/restclient-migration/SKILL.md
```

The original is preserved as `original-SKILL.md` here for traceability and side-by-side completeness review.

## Schema

`procedure.schema.json` — the AIP **Procedure** schema, copied from `.claude/skills/aip/assets/aip-schemas/procedure.schema.json`. The skill is a migration runbook executed step by step; Procedure is the right shape (no checklist or decision-table semantics that would push toward Rulebook).

## Conversion decisions

### Body kept lean; patterns live in references/

The original SKILL.md is ~330 lines of mostly worked code examples (before/after for each call shape, configuration, error handling, complete migration). Inlining all of that in the YAML body would defeat progressive disclosure — every invocation would pay the full token cost on first read. Instead:

- `references/migration-patterns.md` holds all the before/after code blocks, the comparison table, configuration recipes, error-handling pattern, and the worked end-to-end example.
- Step 1 (`load-migration-patterns`) tells the agent to load that file before editing any code.

This preserves every code example from the original; nothing was dropped.

### No `scripts/`

The original is pure knowledge transfer — no thresholds, lookup tables, or numeric rules to encode. Pattern matching ("does this call site look like a GET-with-headers?") is best done by the agent reading Java source, not by a brittle regex script that would mis-classify any non-trivial code. The AIP best-practices rule about scripting conditional logic doesn't apply because the conditions are linguistic over real Java code, not over structured inputs.

### Structural changes from original to AIP form

| Source content                              | AIP location                                   |
|---------------------------------------------|------------------------------------------------|
| "Overview" + "Key Differences" table        | `references/migration-patterns.md` (top)       |
| Examples 1–4 (GET, POST, exchange, DELETE)  | `references/migration-patterns.md` § 1–4       |
| "RestClient Configuration" + Using bean     | `references/migration-patterns.md` § 5         |
| "Error Handling" status handlers            | `references/migration-patterns.md` § 6         |
| "Type-Safe Responses"                       | `references/migration-patterns.md` § 7         |
| "Complete Service Migration Example"        | `references/migration-patterns.md` § 8         |
| "WebClient Alternative"                     | `references/migration-patterns.md` § 9 + `do_not_use_when` in SKILL.md |
| Implicit migration *procedure*              | `steps[]` in SKILL.md (new structure)          |
| Implicit gotchas / "don't do this" wisdom   | `anti_patterns` in SKILL.md                    |

The Procedure-style steps (inventory → rewrite → bean → error handling → verify) are new — the source SKILL.md is reference material that assumed the agent would devise its own procedure. Making the procedure explicit gives the agent a checkable execution graph instead of an open-ended "study these examples and apply them" instruction.

### `name` preserved

Per the task contract, `name: restclient-migration` is unchanged so the task's mounted-skill expectation still matches.
