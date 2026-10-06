# source/ — provenance, step-kind choices, deliberate-drop log

## Provenance

Four curated Agent Skills were compiled into this single AIP skill. The
originals live here verbatim:

- `dc-power-flow/SKILL.md` — DC approximations, susceptance matrix, slack
  bus, line flow and loading math.
- `dc-power-flow/scripts/build_b_matrix.py` — reference implementation of
  the B matrix and line-flow helpers (used as a cross-check against the
  compiled script).
- `economic-dispatch/SKILL.md` — generator / gencost column maps,
  objective, Pmin/Pmax, reserve co-optimization, output formats, solver
  choice (CLARABEL vs OSQP).
- `economic-dispatch/references/cost-functions.md` — polynomial/piecewise-
  linear gencost formats, marginal cost, typical values.
- `locational-marginal-prices/SKILL.md` — dual-value extraction, LMP
  scaling by `baseMVA`, negative-LMP sign convention, reserve MCP, binding-
  line threshold, counterfactual-analysis sketch.
- `power-flow-data/SKILL.md` — MATPOWER JSON shape, bus types, per-unit,
  bus-number mapping, reserve fields, branch columns.

They describe one end-to-end workflow: load → B matrix → DC-OPF with
reserves → extract LMPs / binding lines / totals.

## Step-kind choices

The compiled procedure is intentionally minimal — one `execution` step
feeding `end`.

- `execution` (not `client_task`) because every operation is
  deterministic calculation over the typed network inputs: matrix
  construction, convex optimization, dual extraction, threshold tests.
  There is no judgment to delegate; the AIP guidance treats this as the
  textbook case for a script step.
- `end` carries the structured market clearing. Downstream agents and
  scorers can read it directly without further rendering.
- No `decision` or `router`. The source workflow has no branching
  conditions — the same pipeline runs on every valid MATPOWER file.
- No separate B-matrix / dispatch / LMP steps. Splitting them would
  force CVXPY variables and problem state through JSON stdin/stdout
  between steps, which would be slower and far more fragile without any
  routing benefit (each sub-result is a trivial read on the final
  solved problem).

## Deliberate deviations from the source

- **LMP scaling** — the source `locational-marginal-prices/SKILL.md`
  prescribes `lmp = dual_value * baseMVA`. The compiled script uses
  `lmp = dual_value / baseMVA`. Reason: the balance constraint is
  written in per-unit (`Pg_pu - Pd_pu == B @ theta`) while the
  objective is a function of `Pg_MW = Pg_pu * baseMVA`. By KKT the
  dual carries units of `$/(pu·hr) = baseMVA × $/MWh`, so dividing
  recovers `$/MWh`. Verified on the real PGLib case shipped in
  `environment/network.json`: multiplying produced a median LMP of
  ~$323,000/MWh against a $20.5/MWh average marginal cost; dividing
  produces a median of $32.35/MWh with min/max $-264 / $124, matching
  textbook PGLib behavior. The reference `references/dc-opf-formulation.md`
  and the SKILL.md anti-pattern list both document the correct scaling.

## Deliberate-drop log

Every rule, condition, threshold, lookup, and branching bit from the
source skills is encoded either in `scripts/solve_dcopf.py`, in the
`SKILL.md` body (purpose, trigger_when, do_not_use_when, step
descriptions, anti_patterns), or in the two reference files. The items
below are documentation that does not control runtime behavior and is
intentionally not copied into the AIP body.

- `power-flow-data/SKILL.md`: the PV / PQ / slack bus-type overview
  table. The slack handling is encoded in-script (search for TYPE=3);
  PV vs PQ is a distinction the DC approximation flattens away, so the
  table has no decision role.
- `power-flow-data/SKILL.md`: the `get_branch_info` helper exposing
  `resistance`, `susceptance`, `in_service`. DC-OPF ignores `R` and
  `B` (line charging), and all PGLib snapshots we clear here have every
  branch in service. Keeping the fields in the reference's column table
  preserves provenance without inflating the body.
- `power-flow-data/SKILL.md`: the stand-alone `load_network`,
  `get_generators_at_bus`, `find_slack_bus`, `total_load` helpers.
  Their logic is reproduced inline in `scripts/solve_dcopf.py`
  (`load_network`, the `gen_bus` list, slack-bus search, totals sum).
  Extracting them to a shared module would be a one-caller abstraction.
- `power-flow-data/SKILL.md`: file-size shell commands (`wc -l`,
  `du -h`). The script always uses `json.load`; the warning survives as
  the first anti-pattern.
- `economic-dispatch/references/cost-functions.md`: piecewise-linear
  cost (MODEL=1). No PGLib case in scope uses it, and the compiled
  objective raises no cost term for `ncost < 1`. Preserved in the source
  reference verbatim; agents who extend the pack to piecewise cost
  should start there.
- `economic-dispatch/references/cost-functions.md`: the marginal-cost
  formula (`2*c2*P + c1`) and the "typical values" table. Background
  for understanding the formulation; not consulted by the script.
  Available for downstream reasoning in the preserved source doc.
- `economic-dispatch/SKILL.md`: the alternative "global
  generation==load" power-balance constraint. The compiled procedure
  always uses nodal balance (required for LMPs). The source note that
  the global form hides congestion is preserved; the compiled body
  calls out "do not use the global form" as an anti-pattern.
- `locational-marginal-prices/SKILL.md`: the counterfactual-analysis
  code snippet (relaxing a line limit, re-solving, diffing LMPs).
  Out of scope for the single-shot market clearing this pack produces;
  retained in `references/dc-opf-formulation.md` so an agent extending
  the pack has the exact recipe.
- All four source `SKILL.md` descriptions / rationale paragraphs
  ("DC power flow is a linearized approximation…", "LMPs are the
  marginal cost of serving one additional MW…"). The compiled
  `purpose`, step `description`s, and `references/dc-opf-formulation.md`
  cover the same ground with less duplication.
- The `# Important: Handling Large Network Files` warning from
  `power-flow-data/SKILL.md`. Captured as the first anti-pattern.
