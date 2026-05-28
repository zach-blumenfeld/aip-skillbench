# dc-power-flow — AIP conversion notes

## Origin

Converted from the curated Agent Skill at
`vendor/skillsbench/tasks/grid-dispatch-operator/environment/skills/dc-power-flow/`
(see `ORIGINAL_SKILL.md` in this folder for the verbatim source).

The original skill is a knowledge primer for the linearized DC power
flow approximation used in economic dispatch and contingency analysis.
It mixes prose ("what DC power flow assumes") with code snippets
("build the susceptance matrix this way"). For an agent following
this skill end-to-end, the code is the source of truth — the prose
is context.

## Schema

Uses the AIP `procedure` schema (`source/procedure.schema.json`,
`$id`
`https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json`).

DC power flow analysis is naturally expressed as a small execution
graph:

```
build-bus-index ──► build-b-matrix ──► set-up-angle-constraints ──► solve-angles ──► compute-line-flows ──► rank-loading
```

Each node has typed inputs/outputs (`buses`, `branches`, `B`,
`bus_num_to_idx`, `theta`, `line_flows`). Branching is minimal
(slack bus is always type=3; zero-reactance branches are dropped),
so the procedure stays linear with the per-row logic pushed into
`scripts/build_b_matrix.py`.

## Script policy

The original ships `scripts/build_b_matrix.py` with two reusable
helpers — `build_susceptance_matrix(branches, buses)` and
`calculate_line_flows(branches, branch_susceptances, theta,
baseMVA, bus_num_to_idx)`. Both contain the kind of per-row
indexing and per-unit arithmetic AIP wants in scripts, not prose.
The script is copied verbatim and referenced from the procedure's
`build-b-matrix` and `compute-line-flows` steps.

The two remaining scriptable pieces — slack-bus discovery and line
loading-percentage ranking — are short enough that inlining them
in the step `description` does not over-restrict reasoning. They
stay as prose with the exact formula reproduced. If a downstream
solver needs them as helpers, lift into `scripts/` then.

## Content classification

Every distinct piece of the original SKILL.md is classified below.

| Source section                       | Status            | Where it lives in AIP                                                   |
|--------------------------------------|-------------------|-------------------------------------------------------------------------|
| "DC Approximations" (3 bullets)      | Mapped            | `purpose` (one-line summary) + `anti_patterns` (don't violate the trio) |
| "Bus Number Mapping" prose + code    | Mapped            | `steps.build-bus-index` + `scripts/build_b_matrix.py`                   |
| "Susceptance Matrix (B)" code        | Mapped            | `steps.build-b-matrix` (script-backed)                                  |
| "Power Balance Equation"             | Mapped            | `steps.set-up-power-balance`                                            |
| "Slack Bus" code                     | Mapped            | `steps.set-up-angle-constraints`                                        |
| "Line Flow Calculation" code         | Mapped            | `steps.compute-line-flows` (script-backed)                              |
| "Line Loading Percentage"            | Mapped            | `steps.rank-loading` (formula inlined; small, no branching)             |
| "Branch Susceptances for Constraints"| Mapped            | Returned as `branch_susceptances` by `build-b-matrix`                   |
| "Line Flow Limits (for OPF)" code    | Mapped            | `steps.enforce-thermal-limits`                                          |

No deliberate drops.

## Name preservation

`name: dc-power-flow` is preserved verbatim — the grid-dispatch-operator
task mounts the skill by this exact folder/name and would not see a
renamed skill.
