# grpo (AIP-converted) — Source Notes

This skill was converted from the curated Agent Skill at
`vendor/skillsbench/tasks/debug-trl-grpo/environment/skills/grpo/` to AIP format.

## Schema Choice

`procedure.schema.json` (from `assets/aip-schemas/procedure.schema.json`) was
reused — the GRPO training loop maps cleanly onto `steps`, advantage/log-prob/
loss math and hyperparameter guidance map onto step descriptions plus
`decisions` and `search_shortcuts`, and gotchas map onto `anti_patterns`. No
new schema was drafted.

The schema is bundled here so the skill is self-contained even though
`metadata.aip.schemaId` points at the canonical URL.

## Mapping of Source Sections → Compiled Body

| Source SKILL.md section            | Compiled body location                                              |
|------------------------------------|---------------------------------------------------------------------|
| Overview                           | `purpose`                                                           |
| Training Loop (7-step pipeline)    | `steps` (sample-completions … backprop-and-update)                  |
| Advantage Estimation formula/props | `steps.compute-advantages.description` + `decisions` + `anti_patterns` |
| Log-Probability Computation        | `steps.compute-log-probs.description` + `decisions`                 |
| Loss Function (formula + table)    | `steps.compute-loss.description`                                    |
| Key Hyperparameters table          | `search_shortcuts: Key Hyperparameters`                             |
| Available References               | `search_shortcuts: Reference Files`                                 |

## Deliberate Drops

None. All source content is captured.

## Files

- `procedure.schema.json` — bundled AIP schema this skill validates against.
- `original-SKILL.md` — verbatim copy of the curated source SKILL.md, kept for
  provenance and diffing.
