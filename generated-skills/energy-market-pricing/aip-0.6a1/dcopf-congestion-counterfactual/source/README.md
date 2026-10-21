# Source and provenance

This skill was compiled from four curated Agent Skills that together describe one workflow:
a DC-OPF market clearing with reserve co-optimization, run base vs counterfactual (one
line's thermal limit relaxed). The originals are copied verbatim here:

| Path | What it gave the skill |
|------|------------------------|
| `power-flow-data/SKILL.md` | MATPOWER JSON layout, bus types, per-unit, the reserve fields, bus-number mapping, "use json.load, never sed/head" |
| `dc-power-flow/SKILL.md` + `scripts/build_b_matrix.py` | DC approximations, B matrix, slack θ=0, line flow, loading %, flow-limit constraints |
| `economic-dispatch/SKILL.md` + `references/cost-functions.md` | gencost formats, cvxpy formulation, reserve variables and coupling, CLARABEL solver choice |
| `locational-marginal-prices/SKILL.md` | LMP / reserve MCP as duals, negative-LMP semantics, the 99% binding rule, counterfactual recipe |

Target task: `inputs/instruction.md`. An RTO analyst reruns yesterday's day-ahead market
with the 64–1501 line's capacity +20%, then writes `report.json` (base_case,
counterfactual, impact_analysis). The container is a bare Ubuntu 24.04 `python3`
with no numpy, so the solver script bootstraps its own venv.

## Graph and component-kind choices

```
clear-markets (execution) -> by-status (router) -ok-----> write-report (execution) -> end
                                                -failed-> diagnose-failure (client_task) -> end
```

- **clear-markets: execution.** Everything is deterministic numeric work: parsing, the two
  OPF solves, dual extraction, binding-line threshold, deltas and the top-3 ranking. All
  of it goes into one script (`scripts/clear_markets.py`) so the base and counterfactual
  share the same code. It uses cvxpy + CLARABEL, as the source prescribes. The entry
  point is stdlib-only, and if the packages are missing it builds a venv, because the
  container has none and Ubuntu 24.04 blocks system-wide pip (PEP 668). For that
  reason `requires` names only the interpreter: a `packages` list would stop the
  client before the script could bootstrap.
- **Price self-check inside clear-markets.** The script re-solves with ±1 MW of load
  (at the largest-load bus) and ±1 MW of reserve requirement. The dual must fall
  between the left and right finite differences, or the run fails. This guards the
  sign/scale convention (see corrections below).
- **by-status: router** on the script's `status` ("ok"/"failed"). The script reports
  model/data failures as `failed` rather than crashing: target line missing,
  infeasible clearing, solver failure, price check failure, malformed gencost. That
  lets the agent diagnose them. Environment failures (venv/pip) exit non-zero,
  because the runtime must stop on them.
- **write-report: execution.** A deterministic structural check against the task's
  report schema, then the file is written. It is a separate script so the
  report is never written after a failed clearing.
- **diagnose-failure: client_task.** Root-causing a failure (wrong bus numbers? islands?
  load > capacity?) needs open-ended inspection of the file and the task statement. That
  is the agent's judgment, so no fixed answer space is possible.
- No decision step. Every success-path judgment ("is the line binding?", "is
  congestion relieved?") is a numeric threshold the task defines, so it is scripted.

## Corrections to the sources (deliberate; verified on the task data)

1. **LMP sign and scale.** The source computes `lmp = dual * baseMVA` for the per-unit
   balance `pg - pd == B@theta`. With cvxpy that comes out at **−10⁴ ×** the true LMP:
   cvxpy's equality dual is −d(cost)/d(load), and a per-unit row's dual is per pu, so
   the conversion divides by baseMVA rather than multiplying. On network.json the source
   formula gives bus 1 = −323,173 $/MWh, while a +1 MW re-solve gives +32.32. The skill
   writes the balance in MW and takes `LMP = −dual`, which matched the re-solve to the
   cent at buses 1, 2, 64, 1501 and 2142.
2. **congestion_relieved.** The source uses `was_binding_in_base and not
   is_binding_in_cf`. The task defines it as "the adjusted line is not binding in the
   counterfactual (true = not binding)", and the task's definition is used.
3. **Parallel circuits.** The source's limit-scaling loop `break`s after the first
   matching branch. "The line connecting bus A to bus B" means every in-service circuit
   between them, so all are scaled (the task data has exactly one). Their count is reported
   in `target_line.circuits`.
4. **In-service filtering.** The sources never check GEN_STATUS/BR_STATUS (the task file
   has all units in service). The script drops out-of-service generators/branches so
   another instance of the task with outages is cleared correctly.
5. **RATE_A = 0** is treated as unlimited (MATPOWER convention) instead of producing a
   divide-by-zero or an always-binding line.
6. **gencost** handling covers model 2 with NCOST 1–3 (higher orders only if their
   leading coefficients are zero), and model 1 (piecewise linear, epigraph form),
   which the source's cost-functions reference describes but its code never handles.

## Kept as in the sources

b = 1/X, with TAP and SHIFT ignored (the source's DC model). Cost includes c0. Slack =
the first type-3 bus (bus 0 if none). Binding means loading ≥ 99% of RATE_A. LMPs are
rounded to 2 decimals, in file bus order. Cost reduction = base − cf. Deltas = cf − base.
The top-3 list is the 3 most negative deltas, ties broken by bus number.

## Deliberate-drop log

| Source item | Why dropped |
|-------------|-------------|
| economic-dispatch: copper-plate balance `sum(Pg) == total_load` | Task uses nodal DC-OPF; source itself says to use nodal balance with a network. Mentioned in `do_not_use_when`. |
| economic-dispatch: `generator_dispatch` output format and `totals` block | Not part of report.json. Total generation/reserve MW is kept in `diagnostics`. |
| economic-dispatch: operating margin | Not part of report.json; the definition is kept in `references/market-model.md` for explanation. |
| power-flow-data: `wc -l` / `du -h` file-size check | The script prints sizes in diagnostics; the MANIFEST gives file sizes. |
| power-flow-data: helper functions `get_generators_at_bus`, `find_slack_bus`, `get_branch_info`, `total_load` | Re-implemented (vectorized) inside `clear_markets.py`; the originals remain here. |
| dc-power-flow: dense `build_b_matrix.py` | Replaced by a sparse equivalent in the script (a 2,869² dense matrix is wasteful). Same math, including b = 0 for X = 0. The original is kept at `source/dc-power-flow/scripts/`. |
| dc-power-flow / LMP prose on "why" (economic intuition, DC assumptions) | Background; condensed into `references/market-model.md`, which is loaded for diagnosis. |
| cost-functions.md typical-values table | Background; kept verbatim in `references/cost-functions.md`. |
| PGLib-OPF provenance link | Background; mentioned in references/market-model.md header. |

## Functional test (authoring session)

- Real `network.json`, 64–1501, +20%: base $2,965,637.91/h, cf $2,961,759.38/h,
  reduction $3,878.53/h. The line goes from 100% loaded (binding) to 87.1%, so
  congestion_relieved = true. Largest drops are at buses 64, 629 and 676; the reserve
  MCP is 0 (reserve not scarce; confirmed by re-solve). Each run takes about 2 s plus
  about 20 s for the first-time venv bootstrap.
- Variants: quadratic costs, an offline unit, reversed line orientation, +1% load, and
  a scarce reserve requirement (MCP $29.11, matching the re-solve) all clear correctly.
  Missing line 64–1502, +3% load (infeasible without load shedding) and an impossible
  reserve requirement all route to diagnose-failure.
