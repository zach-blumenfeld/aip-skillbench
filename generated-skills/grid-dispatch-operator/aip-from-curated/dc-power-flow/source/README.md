# dc-power-flow — AIP conversion notes

## Origin
Transcribed from the curated SkillsBench skill at
`vendor/skillsbench/tasks/grid-dispatch-operator/environment/skills/dc-power-flow/`.
The source SKILL.md (preserved here as `original-SKILL.md`) is a markdown reference
of DC power flow formulas and code snippets. It ships one helper script
(`scripts/build_b_matrix.py`) used for two deterministic operations:
building the susceptance matrix and computing post-solve line flows.

## Schema choice
Uses **procedure.schema.json** (bundled). DC power flow as presented in the source is
a sequence of building blocks an agent invokes while assembling a DC-OPF problem
(load arrays → build B → fix slack → write nodal balance → write line limits → solve →
compute flows). That maps cleanly to a procedure graph with script-backed nodes for the
deterministic numeric parts and prose nodes for the cvxpy-flavored formulation parts.

## Script vs. prose decisions
- **Scripted** (`scripts/build_b_matrix.py`, kept verbatim from source):
  - `build_susceptance_matrix(branches, buses)` — deterministic numeric assembly,
    includes the bus_number → 0-indexed mapping that every downstream step needs.
  - `calculate_line_flows(branches, branch_susceptances, theta, baseMVA, bus_num_to_idx)` —
    deterministic post-solve numerics (flow_MW, limit_MW, loading_pct per branch).
- **Prose** (no script):
  - Slack bus pinning — one-line lookup against a column; embedding it in a script
    would force the agent to import a helper for a single line of code while still
    needing to add the constraint to its own cvxpy `constraints` list.
  - Nodal power balance — depends on the agent's choice of decision-variable layout
    (per-generator vs per-bus injection) and on which optimization framework it
    chose. Encoding this as a script would over-restrict.
  - Line thermal limits — likewise framework-dependent. The two linear inequalities
    `-rate <= flow <= rate` are short enough that the prose snippet is sufficient.

## Mapping
Every distinct section of `original-SKILL.md` is captured in the AIP body:

| Source section                       | Where it appears in AIP body                                  |
|--------------------------------------|---------------------------------------------------------------|
| DC Approximations                    | `purpose` (lossless / flat-voltage / small-angle named)       |
| Bus Number Mapping                   | `build-susceptance-matrix` step output + `anti_patterns`      |
| Susceptance Matrix (B)               | `build-susceptance-matrix` step (scripted)                    |
| Power Balance Equation               | `formulate-nodal-power-balance` step (prose + cvxpy snippet)  |
| Slack Bus                            | `identify-slack-bus` step (prose snippet) + `anti_patterns`   |
| Line Flow Calculation                | `compute-line-flows` step (scripted)                          |
| Line Loading Percentage              | `compute-line-flows` step (included in script output)         |
| Branch Susceptances for Constraints  | `build-susceptance-matrix` outputs (`branch_susceptances`)    |
| Line Flow Limits (for OPF)           | `formulate-line-limits` step (prose + cvxpy snippet)          |

No content was dropped.

## Frontmatter
`name: dc-power-flow` is preserved verbatim — the SkillsBench task mounts the skill
by that exact directory name.
