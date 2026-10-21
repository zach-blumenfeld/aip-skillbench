# Source material and distillation log: dcopf-reserve-dispatch

## Provenance

Compiled on 2026-10-20 from three curated Agent Skills that describe one workflow: Grid Dispatch Operator, i.e. DC-OPF dispatch with spinning reserves on a MATPOWER `network.json`, producing `report.json`. The originals are copied verbatim here:

| Path | What it contributes |
|---|---|
| `power-flow-data/SKILL.md` | MATPOWER/PGLib-OPF format, the large-file handling rule, bus types, per-unit, the loader with reserve fields, bus-number mapping, slack lookup, branch fields, total load |
| `dc-power-flow/SKILL.md` | DC approximations, the B matrix, nodal balance, the slack reference, line flow, loading %, line-limit constraints |
| `dc-power-flow/scripts/build_b_matrix.py` | B-matrix and line-flow helpers (x = 0 skipped, loading 0 when RATE_A = 0) |
| `economic-dispatch/SKILL.md` | gen/gencost columns, the cost polynomial by NCOST, the cvxpy formulation, reserve co-optimization (cap, coupling, requirement), operating margin, output format, totals, solver choice (CLARABEL, not OSQP) |
| `economic-dispatch/references/cost-functions.md` | polynomial and piecewise-linear gencost formats, marginal cost, typical coefficients |

The skill was tested against the task's real `network.json` (2869 buses, 510 generators, 4582 branches, all quadratic-format costs with c2 = 0) inside the task's `ubuntu:24.04` container. That container has only bare python3, pip and venv, so the script self-bootstraps a venv.

## Component kinds

| Component | Kind | Why |
|---|---|---|
| Read the task statement, locate paths | client_task | Free text, and paths differ per task instance |
| `requirements_fit` (choice: standard / extra_outputs / extra_constraints) | decision | Judging the task statement against the fixed capability list. The answer space is fixed and it drives the step 6 branch |
| `matpower_branch_model` (noul) | decision | Whether the wording demands taps/phase shifts is a judgment. The answer maps to a script flag |
| Inspect: counts, adequacy and infeasibility precheck, data oddities | execution (`dispatch.py inspect`) | Deterministic arithmetic over the JSON. Replaces the source's "quick summary" snippet and the manual `wc`/`du` checks |
| DC-OPF + reserve solve, verification, report arithmetic, top-N ranking, margin | execution (`dispatch.py solve`) | All source formulas are deterministic code. A maintained solver (cvxpy + CLARABEL) is used, as the source prescribes |
| Exit-code branching (0/1/2/3) | script result + body rules | The rules are deterministic over the script's typed output |
| Extend the report or the model | client_task | Only for non-standard tasks: generated code or fields |
| Re-check a report | execution (`dispatch.py check`) | A deterministic validator for any report, including hand-edited ones |
| Deliver a summary | client_task | Generated text |

One script file holds all three subcommands because they share the loader, model builder, flow and verification code. `build_b_matrix.py` is not mirrored into `scripts/`: its two functions are re-implemented as vectorized sparse code in `build_model` and `line_flows` (a dense 2869×2869 loop is slow). The original stays here.

## Design choices beyond the sources (with rationale)

- **MW variables instead of per-unit Pg.** This is equivalent and better conditioned. Checked against a literal source-style per-unit formulation on the real network: the same cost (2,965,637.9 $/h) and max |ΔPg| = 0.005 MW.
- **Cost recomputed from the dispatch** instead of `prob.value`. They are equal at the optimum. Recomputing also lets `check` validate edited reports.
- **Out-of-service units** (gen col 7 = 0) are pinned to 0 output and 0 reserve, are still listed, and are excluded from cost and margin. **Out-of-service branches** (col 10 = 0) and x = 0 branches carry no flow. **RATE_A = 0** is treated as unlimited (MATPOWER convention): no constraint, and the line is not ranked. The source loads `in_service` but never applies it.
- **One angle reference per island** (the slack bus if the island has one) keeps multi-island cases solvable.
- **Missing reserve fields** mean a requirement of 0 and capacity 0, with a warning.
- **Top-line ties** are broken deterministically (loading rounded to 2 decimals, then branch order), and the tie count is reported. The real case has 23 lines at 100%.
- **Solver fallback chain** is CLARABEL → HiGHS (LP only) → ECOS → SCS. On failure, a re-solve without line limits diagnoses whether transmission or adequacy causes the infeasibility. This replaces the source's copper-plate `sum(Pg) == load` variant as a diagnostic.
- **`--branch-model matpower`** (b = 1/(x·tap), phase-shift injections) is opt-in. The default keeps the source's b = 1/x.

## Completeness walk: deliberate drops

Every rule, threshold, column index, formula and branch in the sources is in `SKILL.md` or `scripts/dispatch.py`. Dropped on purpose:

| Source item | Why dropped |
|---|---|
| power-flow-data: `wc -l` / `du -h` size check | `inspect` gives counts directly. The "never read line-by-line" rule is kept |
| power-flow-data: "Specified / Solved" columns of the bus-type table | AC power-flow background; DC dispatch only needs the slack type. Type codes are kept in the gotchas |
| power-flow-data: Q and S per-unit conversions | Reactive power and MVA are not used in DC dispatch. The P conversion is kept |
| power-flow-data: `get_branch_info` fields r, line-charging b | Ignored by the DC approximation, which is stated in the body |
| dc-power-flow description: "sensitivity analysis" | Not elaborated anywhere in the source, and not needed for this task |
| build_b_matrix.py CLI output (matrix symmetry / nnz print) | Debug output with no task use |
| cost-functions.md: worked example ($1125/hr at 50 MW) | Illustration. The formula itself is in the body, and the script's `gen_cost_value` was verified on a hand-computed case |
| cost-functions.md: typical coefficient table by technology | Descriptive; not needed to compute or validate a dispatch |
| economic-dispatch: the `pmax_MW = gen[8]` snippet style and the explicit cvxpy code | Implemented in the script. The body states the model in math form |

## Functional test log (2026-10-20, in this authoring session)

Fresh-agent testing was not done: the authoring instructions forbid spawning agents, so the author walked the skill directly.

- **Real `network.json`, in the ubuntu:24.04 container.** Bootstrap OK. `solve` exit 0 with CLARABEL optimal: cost 2,965,637.89 $/h, load = generation = 144,839.06 MW, reserve 5,939.98 MW (≥ 5,923.5), margin 68,308.96 MW, 23 binding lines. `check` passes. Decisions for the task statement: `requirements_fit` = standard, `matpower_branch_model` = false.
- **`--branch-model matpower`:** exit 0, cost 2,965,331.81. `check` with the same flag passes.
- **Hand-built 5-bus case** (non-contiguous bus numbers, 2 islands, offline unit, offline branch, RATE_A = 0, linear + piecewise + constant cost, with and without reserve fields): matches a hand solution (cost 1712, line 10–30 binding at 70 MW, margin 160).
- **Infeasible reserve** gives exit 2 with `feasible_without_line_limits` false. **Infeasible line rating** gives exit 2 with true. A **cubic cost** gives exit 1. **Offline bootstrap** gives exit 1 with a clear message. A **forced check failure** gives exit 3.
- **`check` on tampered reports:** changed dispatch, cost-only change, missing key all exit 3 with specific errors.
- **Client branches:** `extra_outputs` (LMPs added from `--details`, then `check` passes) and `extra_constraints` (a script copy with an added constraint solves).
