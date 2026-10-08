# dc-opf-market-clearing — source provenance

## Provenance

Compiled 2026-10-08 from four curated Agent Skills that together describe one workflow
(energy-market pricing on a MATPOWER/PGLib `network.json`: DC-OPF with reserves -> LMPs and
reserve price -> binding lines -> counterfactual impact). Originals copied verbatim:

| Source | Files |
|---|---|
| `power-flow-data/` | `SKILL.md` (data format, large-file handling, bus types, per-unit, reserve fields, bus mapping, helpers) |
| `dc-power-flow/` | `SKILL.md` (DC approximations, B matrix, balance, slack, flows, loading, limits), `scripts/build_b_matrix.py` |
| `economic-dispatch/` | `SKILL.md` (gen/gencost columns, cvxpy objective, limits, reserves, operating margin, output format, solver), `references/cost-functions.md` |
| `locational-marginal-prices/` | `SKILL.md` (LMP from duals, sign meaning, reserve MCP, binding lines, counterfactual method) |

Environment facts used (from the task's `environment/`): container is `ubuntu:24.04` with only
`python3`, `python3-pip`, `python3-venv` (no numpy/scipy/cvxpy; system pip blocked by PEP 668);
input `/root/network.json` (1.4 MB full file: 2869 buses, 510 gens, 4582 branches, all gencost
MODEL 2 / NCOST 3 with c2 = 0, reserve fields present, 614 extra parallel circuits, 531 rows with nonzero
TAP (496 != 1.0), 12 with SHIFT, contiguous bus numbers, one slack bus).

## Procedure graph and step-kind choices

```
parse-request (client_task) -> inspect-network (execution) -> inputs-gate (router)
   true  -> solve-market (execution)          false -> fix-inputs (client_task) -> solve-market
solve-market -> solve-gate (router): optimal -> write-report (client_task) -> end
                                     failed  -> diagnose-failure (client_task) -> end
```

- **parse-request — client_task.** Turning a free-text task into a path, output path, report schema,
  and structured modifications is extraction/generation over unbounded text; no fixed answer space.
- **inspect-network — execution.** Deterministic checks (keys present, bus references resolve,
  capacity vs load, reserve capacity vs requirement, unsupported cost models, parallel circuits,
  counterfactual target resolution). Stdlib only, so it runs before any dependency bootstrap.
- **inputs-gate / solve-gate — routers** on script-produced values (`inputs_ok`, `solve_status`).
  No decision step: both branch conditions are computed deterministically by the scripts, so a
  judgment call would only add noise.
- **fix-inputs — client_task.** Repairing a mistyped path or modification needs re-reading the request.
- **solve-market — execution.** All numerics (B matrix, OPF, duals, flows, binding test, operating
  margin, counterfactual deltas, congestion relief, finite-difference check) are scriptable.
  One script, because base and counterfactual share the whole model.
- **write-report — client_task.** The required output schema is task-specific; the agent maps the
  canonical draft (`report_draft.json`, source field names) to it with a short script.
- **diagnose-failure — client_task.** Open-ended troubleshooting.

## Deliberate deviations from the sources (with evidence)

1. **LMP conversion.** `locational-marginal-prices` says `lmp = dual_value * baseMVA` for the
   per-unit balance. Verified on the real network with cvxpy 1.9 (CLARABEL and HiGHS agree): that
   gives values like -323,173 $/MWh, while a +1 MW finite-difference re-solve gives +32.32 $/MWh at the
   same bus. cvxpy's Lagrangian is f + y'(lhs - rhs), so LMP = -dual / baseMVA for the per-unit form.
   The script writes the balance in MW and uses LMP = -dual, and re-checks one bus by finite
   difference on every run (`self_check`). Recorded in `references/dcopf-market-method.md` and
   `anti_patterns`.
2. **Vectorized sparse model** instead of per-bus Python loops and a dense B matrix (2869^2 dense is
   wasteful); same constraints. The dense `build_b_matrix.py` stays in `source/` as reference.
3. **Dependency bootstrap.** The container has no numpy/cvxpy; the script creates a venv and pip
   installs `numpy scipy cvxpy clarabel` (about 2 min cold), then re-runs itself.
4. **Out-of-service handling.** Branches with BR_STATUS 0 are excluded and gens with GEN_STATUS 0 are
   fixed at 0 (MATPOWER semantics; the sources ignore status). No effect on the task network (all in
   service).
5. **Additional cost models.** NCOST 1/2/3 polynomial handled by padding (as in the source branches);
   MODEL 1 piecewise linear handled via epigraph (the source only documents the format); NCOST > 3
   rejected with a clear error instead of silently mis-reading coefficients.
6. **RATE_A = 0** treated as unlimited (MATPOWER convention) instead of a 0 MW limit; none in the task network.
7. **Counterfactual generality.** `line_limit` (factor or absolute), `bus_load`, `reserve_requirement`
   modifications. `line_limit` keeps the source semantics: direction-insensitive match, first matching
   row only (`match: "all"` optional; inspector warns when parallel circuits exist).
8. **Kept from sources on purpose:** b = 1/x with TAP and SHIFT ignored (the sources' DC model; the
   task network has taps, but the reference method ignores them), binding threshold 99%,
   congestion_relieved = binding in base and not in counterfactual, CLARABEL as the solver.

## Completeness check (source item -> where it lives)

| Source item | Location in pack |
|---|---|
| power-flow-data: MATPOWER/PGLib origin | `references/matpower-network-format.md` title; description |
| Large files: never read line by line, use json.load, quick summary, wc/du | anti_patterns; `inspect_network.py` (json.load + summary); matpower ref; parse_request template ("do not open or print") |
| Bus types table (slack/PV/PQ) | matpower ref bus table; inspector `bus_type_counts` |
| Per-unit conversions | matpower ref; solver (Pg pu, MW conversions) |
| load_network() fields incl. reserves | `solve_market.load_network` |
| Reserve data table | matpower ref; solver reserve block; inspector checks |
| Bus number mapping (all three skills) | solver `bus_num_to_idx`; anti_patterns; matpower ref helpers |
| get_generators_at_bus / find_slack_bus / get_branch_info / total_load helpers | matpower ref Helpers; solver (Cg matrix, slack search, branch fields) |
| dc-power-flow: DC approximations | method ref; do_not_use_when (AC needs) |
| B matrix construction, x = 0 skip | solver (sparse B, b = 0 when x = 0); method ref |
| Power balance equation | solver `balance`; method ref |
| Slack bus theta = 0 (type 3) | solver; inspector warns if not exactly one |
| Line flow, loading %, RATE_A | solver `line_flows`; method ref |
| Branch susceptances list | solver `b` vector; method ref |
| Line flow limits as two linear constraints | solver; method ref |
| build_b_matrix.py (build B, line flows, CLI) | reimplemented sparse in solver; original in `source/dc-power-flow/scripts/` |
| economic-dispatch: gen columns 0/8/9 | matpower ref gen table; solver |
| gencost format, NCOST 3/2/constant handling | solver cost block; matpower ref; `references/cost-functions.md` |
| Cost = c2 P^2 + c1 P + c0, P in MW | solver objective; method ref |
| Gen limits in per-unit | solver |
| System balance (no network) vs nodal balance | method ref Constraints |
| Reserve co-optimization (Rg >= 0, <= cap, Pg+Rg <= Pmax, sum >= R) | solver; method ref |
| Operating margin = sum(Pmax - Pg - Rg), "uncommitted headroom" | solver `operating_margin_MW`; method ref |
| Dispatch output format (id, bus, output_MW, reserve_MW, pmax_MW; 2 dp) | solver `generator_dispatch`; report draft |
| Totals (cost, load, generation, reserve) | solver `totals`; report draft |
| CLARABEL; OSQP may fail | solver order (CLARABEL first); anti_patterns; method ref |
| cost-functions.md (poly, PWL, example, marginal cost, typical values) | copied verbatim to `references/cost-functions.md`; PWL support in solver |
| LMP = dual of balance; store constraint refs | solver; method ref (with corrected sign/scale) |
| LMP sign convention, negative LMP causes, large magnitudes valid | method ref; anti_patterns; write_report sanity list |
| Reserve MCP = dual of reserve constraint | solver; self_check; method ref |
| Binding lines >= 99%, x != 0, rate > 0, output fields | solver `BINDING_THRESHOLD`; report draft |
| Counterfactual 4-step method, +20% first match either direction | solver `apply_modifications` / `compare`; parse_request template; method ref |
| cost_reduction = base - cf (>= 0), LMP delta sign meaning | solver `compare` (+ warning if relaxing raises cost); write_report sanity list |
| congestion_relieved definition | solver `compare`; method ref |
| Economic intuition (relaxing can't raise cost; shadow price; LMP convergence) | method ref; write_report sanity list |

## Deliberate-drop log

| Dropped | Why |
|---|---|
| Source frontmatter descriptions (4) | Merged into this skill's single description / trigger_when. |
| "Example usage with IEEE 14-bus test data" CLI banner and its prints (non-zeros, symmetry) in `build_b_matrix.py` | Debug output, not part of the workflow; original kept in `source/`. |
| `wc -l` / `du -h` as separate guidance | Kept only as a one-line aside in the matpower ref; the inspector reports sizes that matter. |
| Per-generator Python loop formulation code blocks | Same math implemented vectorized in the solver; loop form is redundant. |
| "Typical Values" table usage guidance | Kept verbatim in `references/cost-functions.md`; not used by the procedure (costs come from the file). |

## Functional test log

- `aip run` with `scratch/start.json` (line 64-1501 +20%): parse-request -> inspect-network ->
  solve-market -> write-report -> end. Base $2,965,637.91/h, counterfactual $2,961,759.38/h,
  congestion relieved; LMP and reserve MCP finite-difference checks agree. fix-inputs branch
  (unknown line) and diagnose-failure branch (infeasible +100 GW load) also run to `end`.
- Cold bootstrap from a bare Python 3.14 (no numpy): venv + pip + solve in ~2 min 20 s.
- Synthetic 4-bus network (non-contiguous bus numbers, quadratic, linear, piecewise-linear costs, no
  reserve data, out-of-service gen, unlimited line): LMPs match hand-computed marginal costs.
- Two fresh agents (line 2612-202 +15%; reserve requirement x3) reached `end` with no script errors.
  Their feedback led to: write-report generalized to tightening counterfactuals (`cost_change`),
  a field index for quantities not in the draft, a rule that every asked-for quantity must appear,
  handling of zero-delta ties in top-N lists, a relative-path rule in parse-request, and a
  finite-difference check of the counterfactual (`self_check_cf`; reserve MCP 21.05 confirmed).
