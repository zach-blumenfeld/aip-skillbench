# Source — dc-power-flow (AIP conversion)

## Intent

Convert the curated SkillsBench `dc-power-flow` Agent Skill into AIP format,
preserving every domain fact, equation, MATPOWER column convention, and code
pattern from the original `SKILL.md`. The downstream consumer is an agent that
must solve `energy-market-pricing` (a DC-OPF + LMP analysis task that depends
on building B, computing line flows, and enforcing thermal limits).

## Files

- `original-SKILL.md` — verbatim copy of the source skill, used as the
  authoring reference and the line-by-line completeness target.
- `procedure.schema.json` — bundled copy of the AIP `procedure` schema this
  skill validates against.

## Schema selection

Used the AIP `procedure` schema. The source SKILL.md describes a structured,
script-backed procedure for DC power flow: load network → build B → identify
slack → power-balance / flows / loading / limits. Steps form an execution
graph with shared `bus_num_to_idx`, `B`, and `branch_susceptances` artifacts
flowing between nodes — exactly what `procedure` is designed for. No new
schema needed.

## Script changes vs. source

`scripts/build_b_matrix.py` keeps the original
`build_susceptance_matrix` and `calculate_line_flows` functions verbatim.
Added a small `find_slack_bus(buses)` helper so the `identify-slack-bus` AIP
step can be script-backed instead of prose (lookup logic — fits the
"scriptable logic belongs in scripts" guidance). The `__main__` block was
extended to also print the resolved slack index.

## Completeness mapping (source → AIP body)

| Source section                       | Where it lives in the AIP body                       |
|--------------------------------------|------------------------------------------------------|
| DC Approximations (lossless, flat V, small θ) | `purpose` summary + `anti_patterns` (no V/Q reasoning) |
| Bus Number Mapping (non-contiguous IDs)       | `build-susceptance-matrix` step (script) + `anti_patterns` + `scenarios` (case300) |
| Susceptance Matrix (B) construction           | `build-susceptance-matrix` step (script-backed)      |
| Power Balance Equation Pg-Pd = B[i,:]·θ       | `formulate-power-balance` step description           |
| Slack Bus identification (type=3, θ=0)        | `identify-slack-bus` step (script-backed via `find_slack_bus`) + `anti_patterns` |
| Line Flow Calculation b·(θf-θt)·baseMVA       | `compute-line-flows` step (script-backed `calculate_line_flows`) |
| Line Loading % (abs(flow)/rate*100)           | `compute-line-flows` step (handled in `calculate_line_flows`) + `anti_patterns` (guard rate==0) |
| Branch Susceptances list storage              | output of `build-susceptance-matrix`                 |
| Line Flow Limits for OPF (-rate ≤ flow ≤ rate)| `enforce-thermal-limits` step description + `modes.dc-opf` |
| MATPOWER column conventions (X=col 3, RATE_A=col 5) | `anti_patterns` + step descriptions             |

No deliberate drops.
