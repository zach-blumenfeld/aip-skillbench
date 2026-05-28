# Source materials — economic-dispatch (AIP conversion)

This folder is the canonical record of how the AIP-format `SKILL.md` at the
root of this skill was built.

## Inputs

- `ORIGINAL_SKILL.md` — verbatim copy of the curated SkillsBench skill at
  `vendor/skillsbench/tasks/energy-market-pricing/environment/skills/economic-dispatch/SKILL.md`.
  This is the human-readable source the AIP body was compiled from.
- `procedure.schema.json` — the AIP `procedure` schema the new `SKILL.md`
  validates against. Bundled locally so the skill is self-contained even
  though `$id` points at the canonical shared URL.

## Schema choice

The original SKILL.md describes a multi-step optimization workflow — parse
MATPOWER inputs → build CVXPY objective → add constraints (limits, balance,
optional reserves) → solve → format outputs. That maps cleanly to the
`procedure` schema (purpose / trigger_when / steps / decisions / anti_patterns).
No new schema was drafted.

## Mapping notes

- Reference content kept under the top-level `references/cost-functions.md`
  (copied verbatim from the curated skill). The AIP body links to it from
  the `parse-cost-functions` step rather than inlining piecewise-linear /
  marginal-cost / typical-coefficient material — progressive disclosure.
- Code snippets in the original markdown sections are preserved inside step
  `description` block scalars so the agent still has copy-pasteable code.
- The original had no explicit "when to use" or "anti-patterns" sections;
  those were synthesized from the section guidance (e.g., the bus-number
  mapping warning, the NCOST branching, the OSQP-vs-CLARABEL note, the
  operating-margin definition).

## Frontmatter `name`

Kept as `economic-dispatch` — the mounted skill name must match what the
SkillsBench task environment expects.
