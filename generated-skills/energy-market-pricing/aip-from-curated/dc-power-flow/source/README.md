# dc-power-flow — AIP authoring notes

## Source

`original-SKILL.md` is a verbatim copy of the curated SkillsBench skill at
`vendor/skillsbench/tasks/energy-market-pricing/environment/skills/dc-power-flow/SKILL.md`.
It is preserved unmodified for traceability when re-authoring the AIP body.

## Schema choice

Validates against `procedure.schema.json` (bundled here for self-containment;
`$id` points at the canonical v0.2 URL). DC power flow is a linear sequence
of computation steps — assumptions, matrix construction, equation setup,
slack pin, flows, loading, limits — which is the shape the procedure schema
is designed for. `steps` capture the workflow; `anti_patterns` capture
"don't do this" rules surfaced in the source prose.

## Source-to-body mapping

Every section of `original-SKILL.md` is captured in the AIP body:

| Source section                       | AIP body location                          |
|--------------------------------------|--------------------------------------------|
| Opening paragraph                    | `purpose`                                  |
| DC Approximations (3 items)          | step `apply-dc-approximations`             |
| Bus Number Mapping (+ code)          | step `build-bus-number-mapping`            |
| Susceptance Matrix (B) (+ code)      | step `build-susceptance-matrix`            |
| Power Balance Equation               | step `write-power-balance`                 |
| Slack Bus (+ code)                   | step `pin-slack-bus`                       |
| Branch Susceptances for Constraints  | step `store-branch-susceptances`           |
| Line Flow Calculation (+ code)       | step `calculate-line-flows`                |
| Line Loading Percentage (+ code)     | step `calculate-loading-percentage`        |
| Line Flow Limits (for OPF) (+ code)  | step `enforce-line-flow-limits`            |
| (Derived from above)                 | `anti_patterns` (bus-mapping, slack pin, X != 0, R != 0) |

No content was dropped.

## Frontmatter

`name` is unchanged (`dc-power-flow`) — the SkillsBench task mounts the
skill by that name, so renaming would break the task.
