# Source Notes — economic-dispatch (AIP conversion)

## Origin

Converted from the curated SkillsBench skill at
`vendor/skillsbench/tasks/grid-dispatch-operator/environment/skills/economic-dispatch/`.

Source materials in this folder:
- `SOURCE_SKILL.md` — original freeform-markdown SKILL.md
- `procedure.schema.json` — bundled AIP procedure schema this skill validates against
- `../references/cost-functions.md` — copied verbatim from the source

## Conversion logic

The original SKILL.md is a runbook for solving economic dispatch on a MATPOWER
network: parse the data, build a CVXPY cost objective with variable NCOST, add
generator and reserve constraints, solve with CLARABEL, format report fields.

Schema choice: **procedure** — the skill is a multi-step optimization workflow
with clear inputs and outputs between steps. `procedure.schema.json` is reused
unmodified from the AIP shared schemas.

Script extraction: per AIP best practices, every step that contains
domain-specific logic (cost-function NCOST branching, MW↔per-unit conversions,
capacity-coupling math, output-formatting tables) is backed by a single helper
module `scripts/economic_dispatch.py`. The agent imports its functions to
build the optimization problem and format the report.

## Completeness mapping (source → AIP)

| Source content | AIP location |
|---|---|
| Generator data indices table | `references/matpower-arrays.md` + script docstrings |
| Bus-number-to-index code | Step `build-bus-index` + `bus_num_to_idx` helper |
| Cost function format + NCOST handling | Step `build-cost` + `build_cost_objective` helper |
| Generator limits | Step `build-generator-limits` + `build_generator_limit_constraints` helper |
| Power balance constraint | Step `build-power-balance` + `build_simple_power_balance` helper |
| Reserve co-optimization | Step `build-reserves` + `build_reserve_constraints` helper |
| Operating margin | Step `format-output` + `compute_operating_margin` helper |
| Dispatch output format | Step `format-output` + `format_generator_dispatch` helper |
| Totals calculation | Step `format-output` + `compute_totals` helper |
| Solver selection (CLARABEL) | Step `solve` + `solve_problem` helper |
| Cost-functions reference doc | `references/cost-functions.md` (copied verbatim) |
| Note about composing with dc-power-flow | `integrations` block |

No source content deliberately dropped.
