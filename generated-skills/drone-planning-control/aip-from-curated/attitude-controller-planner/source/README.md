# Source materials and authoring notes

This AIP skill is a structured port of the curated SkillsBench skill at
`vendor/skillsbench/tasks/drone-planning-control/environment/skills/attitude-controller-planner/SKILL.md`
(bundled here as `source/SKILL.md`).

## Schema choice

Used `procedure.schema.json` (bundled here as `source/procedure.schema.json`). The
source skill is a structured procedure: implement two cooperating modules
(attitude planner, attitude controller) with specific math, then wire them into
the simulation loop. Steps are sequential, with a tuning sub-procedure and a
signal→action tuning table — a natural fit for `steps`, `decisions`, and
`anti_patterns`.

## Source → AIP body mapping

| Source section | AIP body location |
|---|---|
| Overview (two-module structure) | `purpose` |
| Attitude Planner — Implementation Logic | `steps[name=attitude-planner]` |
| Attitude Controller — Implementation Logic | `steps[name=attitude-controller]` |
| Gain Tuning paragraph (starting values) | `steps[name=tune-gains]` |
| Integration in Main Loop (code snippet) | `scenarios` (worked example) |
| Tuning Guidelines table | `decisions` (signal → action) |
| Critical Design Rules | `anti_patterns` |

## Deliberate drops

None — every source line is mapped. The `Integration in Main Loop` Python
snippet is preserved verbatim inside a `scenarios[].action` block scalar so the
calling convention (creating `att_integral` once, passing it in every iter)
stays visible.

## Frontmatter

- `name` preserved exactly as `attitude-controller-planner` so the task's
  mounted skill name continues to match.
- `description` copied verbatim from the source frontmatter.
