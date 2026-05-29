# Source notes — unit-commitment-operating-rules → AIP

This folder bundles the canonical source used to author the AIP version
of `unit-commitment-operating-rules`:

- `original-SKILL.md` — verbatim copy of the curated source skill at
  `vendor/skillsbench/tasks/energy-unit-commitment/environment/skills/unit-commitment-operating-rules/SKILL.md`.
- `procedure.schema.json` — the AIP schema the AIP `SKILL.md` validates
  against (`procedure` family, v0.3a2). Bundled locally per AIP best
  practice so the skill is self-contained.

## Schema choice

`procedure` fits cleanly. The source is a graph of operating-rule
patterns the agent walks during model construction and post-solve
validation. The required fields (`purpose`, `trigger_when`, `steps`)
map to the source's intro, "Use this skill when..." paragraph, and
"Implementation Workflow" section.

No new schema was authored.

## Logic encoded as scripts

The source guide contains:

- Validation rules (binary checks, capacity bounds, transition
  consistency, ramping, min up/down, demand balance, reserve
  requirement, reserve deliverability)
- A startup-cost tier rule (largest lag not exceeding offline duration)
- A piecewise-linear production-cost lookup with clamping rules

All three are decision rules with numeric thresholds and per-period
iteration — the AIP guidance is unambiguous: move them into `scripts/`.
They live at:

- `scripts/feasibility_checks.py`
- `scripts/startup_cost.py`
- `scripts/production_cost.py`

The constraint algebra (capacity, ramping, reserve deliverability,
min up/down, transition logic) is also referenced when *constructing*
the model — not only when validating after the fact. The pattern
formulas stay in `references/constraint-patterns.md`, loaded on
demand, with one-line cues in the body steps.

## Completeness audit (source → AIP)

Walked line-by-line through `original-SKILL.md`. Classification:

- **Mapped** — UC intro paragraph, variable conventions, core feasibility
  checks list, transition logic, capacity/offline zeros, demand and
  renewables, system reserve, reserve deliverability, ramping, min
  up/down, startup costs, production costs, implementation workflow,
  common pitfalls.
- **Schema gap** — none.
- **Body drop** — none.
- **Deliberate drop** — none.

The detailed code snippets from the source moved to
`references/constraint-patterns.md` so the body stays under the AIP
budget; the body cites them at point of use.
