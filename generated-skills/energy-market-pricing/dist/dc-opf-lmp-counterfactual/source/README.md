# Source and provenance

`dc-opf-lmp-counterfactual` was compiled from four curated Agent Skills. They are copied
here verbatim:

| path | content |
|---|---|
| `power-flow-data/SKILL.md` | MATPOWER JSON layout, bus types, per-unit, reserve fields, bus-number mapping, large-file handling (PGLib-OPF data) |
| `dc-power-flow/SKILL.md` + `scripts/build_b_matrix.py` | DC approximations, B matrix, slack, line flows, loading %, flow-limit constraints |
| `economic-dispatch/SKILL.md` + `references/cost-functions.md` | gen/gencost columns, polynomial and PWL costs, cvxpy formulation, reserve co-optimization, operating margin, output formats, solver choice |
| `locational-marginal-prices/SKILL.md` | LMPs and reserve MCP from duals, sign convention, binding-line rule (≥ 99%), counterfactual procedure, economic intuition |

The target task (see the skill's Trigger When) is to clear a DC-OPF with reserves on
`network.json`, relax one line's thermal limit by X%, re-clear, and write `report.json`
with base, counterfactual, and impact sections. The skill was functional-tested on the
real 2869-bus / 510-gen / 4582-branch input, both on the host and inside the task's
`ubuntu:24.04` image. That image has only python3, pip, and venv, so the script
bootstraps its own venv.

## Corrections to the sources, found during testing

1. **LMP dual scaling and sign.** The source computes `lmp = dual * baseMVA` on a per-unit
   balance row. With cvxpy 1.9 this gives −baseMVA² × the true LMP: a 2-bus toy case gave
   −100000 instead of 10 $/MWh, and the real grid gave ±2.6 M $/MWh. The correct value is
   −dual / baseMVA for a per-unit row, or −dual for an MW row. This was verified three ways:
   (a) the toy case, (b) an independent `scipy.optimize.linprog` (HiGHS) solve, whose
   marginals match within $0.005/MWh on all 2869 buses in both cases, and (c) LMP =
   marginal cost at every unconstrained generator. The script poses the model in MW, uses
   −dual, and self-checks with (c).
2. **Per-unit conditioning.** On a synthetic variant with quadratic costs and no reserves,
   the per-unit form failed in both CLARABEL (InsufficientProgress) and HIGHS (QP
   infeasibility errors). The same model posed in MW solves cleanly, so the script uses MW
   throughout and keeps HIGHS as a fallback after CLARABEL. This complements the source's
   note that OSQP fails on ill-conditioned problems and CLARABEL should be preferred.
3. **Parallel circuits.** The source scales the first matching branch and breaks out of
   the loop. The real network has corridors with up to 5 parallel circuits, so the script
   refuses to guess and a decision (`circuit_scope`) chooses instead.
4. **congestion_relieved.** The source defines it as "binding in base and not in cf". The
   task statement defines it as "not binding in the counterfactual". Both are implemented
   (`--relieved-rule`), with the task's wording as the default, and a decision picks
   between them.

## Component-kind choices

| component | kind | why |
|---|---|---|
| Runtime check + venv bootstrap | execution (inside the script) | Deterministic; the container lacks numpy/scipy/cvxpy |
| `inspect` network summary + target-branch lookup | execution | Pure parsing and counting; replaces the source's "quick summary" snippet and `wc`/`du` |
| Study parameters (`circuit_scope`, `dc_model`, `relieved_rule`) | decision (3 choice questions) | Need a reading of the task wording; the answer space is fixed and each answer maps to a CLI flag |
| Market clearing, LMP/MCP, binding lines, counterfactual, impact, report | execution | Numeric optimization, threshold rules, sorting: all deterministic |
| Sanity checks (optimal, LMP = MC, cost not increased, balance, reserve met) | execution | Fixed rules with numeric tolerances, printed as booleans |
| What to do when a check fails | decision, folded into step 4 branches | Branches on the scripted booleans |
| Final summary to the user | client task | Free-text synthesis |

Scalar task parameters (bus numbers, % change, output path) are extracted straight from
the task text and passed as flags. They need no judgment beyond reading.

## Deliberate-drop log

| source item | disposition |
|---|---|
| power-flow-data: `wc -l` / `du -h` file-size commands | Dropped: `inspect` reports the counts, and the body warns never to page through the file |
| power-flow-data: helper functions `get_generators_at_bus`, `find_slack_bus`, `get_branch_info`, `total_load` | Logic folded into the script (Cg incidence matrix, slack lookup, branch columns, inspect totals); the helpers themselves are not needed |
| dc-power-flow `scripts/build_b_matrix.py` | Superseded by the sparse B / Bf construction in `market_counterfactual.py` (same 1/x rule, the same x = 0 skip, and loading = 0 when RATE_A = 0). Kept in `source/` only |
| economic-dispatch: copper-plate balance `sum(Pg) == total_load` | Dropped: the source itself says to use nodal balance for DC-OPF, which this task requires |
| economic-dispatch: dense per-generator Python loops for costs and limits | Replaced by vectorized equivalents (same model, much faster on 500+ generators) |
| economic-dispatch: OSQP warning | Kept as rationale here; the script never uses OSQP |
| cost-functions.md: typical coefficient table | Kept in `references/formulation.md` (context only) |
| locational-marginal-prices: dense `B[i,:] @ theta` per-bus constraints | Replaced by one vectorized sparse constraint whose dual vector gives every LMP |
| Gen/branch status columns (not in the sources) | Added: out-of-service elements are excluded, a MATPOWER convention |
| RATE_A = 0 → unlimited (not in the sources) | Added: MATPOWER convention, used in both the constraints and the binding test |
| Transformer taps / phase shifts / bus GS | Ignored by default to match the source's b = 1/x; available via `--dc-model matpower`, selected by the `dc_model` decision. On the test network the matpower model shifts the cost reduction by about 3% (3879 → 3759 $/h) |
