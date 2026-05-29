# dc-power-flow — AIP conversion notes

Source: `vendor/skillsbench/tasks/energy-market-pricing/environment/skills/dc-power-flow/`
(SKILL.md + `scripts/build_b_matrix.py`).

Target schema: `procedure.schema.json` — the source is a structured procedure
(B-matrix construction → angle solve → flow computation → thermal limits) with
deterministic numeric primitives, which the procedure schema captures cleanly.

## Source → AIP mapping

| Source SKILL.md section          | AIP body location                              |
|----------------------------------|------------------------------------------------|
| Front-matter `name`/`description`| Preserved verbatim (mount-name must match)     |
| "DC Approximations" intro        | `purpose` (folded in)                          |
| "Bus Number Mapping"             | `steps[build-susceptance-matrix]` outputs + anti_patterns (off-by-one) |
| "Susceptance Matrix (B)"         | `steps[build-susceptance-matrix]` (script-backed) |
| "Power Balance Equation"         | `steps[add-power-balance]` (prose; uses agent's optimization variables) |
| "Slack Bus"                      | `steps[set-slack-reference]` (script-backed via find_slack_bus) |
| "Line Flow Calculation"          | `steps[calculate-line-flows]` (script-backed) |
| "Line Loading Percentage"        | folded into `calculate-line-flows` output       |
| "Branch Susceptances for Constraints" | output of `build-susceptance-matrix`      |
| "Line Flow Limits (for OPF)"     | `steps[add-thermal-limits]` (prose)            |

## Script vs prose

Script-backed where logic is deterministic over structured inputs:

- `build_susceptance_matrix(branches, buses)` — matrix assembly + bus mapping
- `calculate_line_flows(...)` — closed-form MW + loading
- `find_slack_bus(buses)` — added during conversion (one-line scan, but worth
  exposing so step graph stays consistent)

Prose where the logic must compose with the agent's optimization framework
(CVXPY/Pyomo variables, model object, constraint list):

- `set-slack-reference` (script finds the index, agent appends the constraint)
- `add-power-balance` (depends on Pg expression built from the agent's gen model)
- `add-thermal-limits` (constraint construction over agent's theta)

## Deliberate drops

None. Every distinct piece of the source SKILL.md mapped into the AIP body
(directly or as an anti-pattern). The MW vs per-unit nuance, slack singularity,
and bus-mapping pitfalls all surface in `anti_patterns`.

## Files

- `procedure.schema.json` — bundled AIP procedure schema (copy of canonical).
- `source-SKILL.md` — original curated SKILL.md (input to this conversion).
