# grid-dispatch — source provenance

## Sources (copied verbatim into this folder)

| path | origin |
|---|---|
| `economic-dispatch/SKILL.md` | curated Agent Skill: cost functions, ED/DC-OPF formulation, reserves, operating margin, output format, solver choice |
| `economic-dispatch/references/cost-functions.md` | curated reference: gencost type 2 / type 1, marginal cost, typical coefficients (also copied to `references/cost-functions.md`) |
| `dc-power-flow/SKILL.md` | curated Agent Skill: DC approximations, B matrix, nodal balance, slack, line flows, loading, line limits |
| `dc-power-flow/scripts/build_b_matrix.py` | curated script: B matrix + per-line flows/loading (logic folded into `scripts/solve_dispatch.py`) |
| `power-flow-data/SKILL.md` | curated Agent Skill: MATPOWER/PGLib-OPF JSON layout, large-file handling, bus types, per-unit, reserve fields, bus mapping |

The three skills describe one workflow (load network → build DC model → least-cost dispatch with
reserves → report), so they compile into one procedure. The target data is
`network.json` (PGLib-OPF, 2869 buses, 510 generators, 4582 branches, all linear costs
`[2,0,0,3,0,c1,0]`, reserve fields present, contiguous bus numbers, 496 branches with TAP
and 12 with SHIFT, all units and branches in service). The pack must also hold for other
files of that format.

## Graph and step-kind choices

1. `scope` — **decision** (start). Whether reserves are co-optimized and whether the network
   (nodal balance + RATE_A limits) is enforced depends on the task wording, a judgment over a
   fixed yes/no answer space. Two nouls in one step; thresholds are lower for
   `co_optimize_reserves` (0.2) because dropping a required reserve constraint makes the answer
   wrong. Run parameters that are just read off the task (paths, number of lines to list) are start
   inputs, not questions.
2. `solve` — **execution**. Everything numeric is scripted: JSON parsing, bus-number mapping,
   gencost decoding (NCOST 3/2/1, piecewise linear), the sparse DC-OPF (B = Aᵀ diag(1/X) A,
   slack θ=0, ±RATE_A), reserve constraints, CLARABEL solve with fallbacks, per-line flows
   and loading, operating margin, rounding, writing the default report, and feasibility checks.
   One script, because the steps share all their data. cvxpy + CLARABEL follow the source's solver
   advice; the model is vectorized with sparse matrices, so the real 2869-bus case solves in about 1 s.
   The container (ubuntu:24.04 + python3/pip/venv only) has no numpy/scipy/cvxpy, so the
   script bootstraps a venv (`~/.cache/grid-dispatch/venv`, override `GRID_DISPATCH_VENV`)
   and re-execs itself. Tested from a bare Python 3.9: about 66 s on first use.
3. `by-status` — **router** on the script's `solve_status` (`optimal` | `failed`).
4. `deliver` — **client_task**. The task's exact output schema/path varies and only the agent
   can reconcile it; the template pins the default schema (the source's output format), forbids
   hand-retyping numbers, and lists the sanity checks.
5. `diagnose` — **client_task**. Failure analysis is open-ended; the script supplies the
   capacity/reserve diagnostics so the agent reasons over facts rather than guesses.
6. `end` — `final_answer`.

## Modelling decisions (not stated in the sources)

- Variables are in MW rather than per-unit (the source uses per-unit Pg × baseMVA). The optimum is
  the same and the conditioning is better.
- Out-of-service generators (GEN_STATUS 0) are fixed at 0 with no reserve; out-of-service
  branches (BR_STATUS 0) are dropped. The source's `get_branch_info` exposes `in_service`
  but never says how to use it; this is the MATPOWER convention.
- RATE_A = 0 means unlimited (MATPOWER convention, consistent with the source's
  `loading_pct = 0 if limit == 0` guard).
- TAP, SHIFT and bus GS are ignored, so `b = 1/X` exactly as in the sources. Documented in
  `references/dc-opf-formulation.md` for tasks that demand the full MATPOWER DC model.
- Reserves are free in the sources' objective, so Σ Rg (and therefore operating margin) was
  non-unique: CLARABEL over-procured by ~16 MW. The script adds a 1e-6 $/MW reserve
  tie-breaker (excluded from reported cost) and solves all-linear-cost cases (LPs) with HiGHS
  first, so Σ Rg equals the requirement exactly. Quadratic costs still use CLARABEL first, per
  the source. CLARABEL and HiGHS agree on cost (2,965,637.9 $/hr on the real file).
- `--matpower-taps` (state key `matpower_taps`) is an opt-in MATPOWER DC model (TAP, SHIFT)
  for tasks that demand it; the default stays with the sources' b = 1/X.
- Solver noise is clipped to limits before rounding, so no rounded output crosses PMIN/PMAX.
- Line entries carry `branch_index` (1-based row) because parallel circuits share from/to.
  `binding_lines` (≥ 99.9 %) is only filled when network-constrained; in copper-plate mode
  over-limit flows are reported as `overloaded_lines`.
- The script has no defaults for the scope flags: a missing key returns `solve_status: failed`
  instead of silently assuming reserves/network. (These last three came from fresh-agent testing.)
- Lines tied at the same loading (many sit at 100 %) are ordered by branch row order, so the
  output is deterministic.

## Completeness check (source item → where it lives)

- Gen columns 0/8/9, gencost columns, NCOST handling, cost in MW → `solve_dispatch.py`
  `_cost_expr`; `references/dc-opf-formulation.md`; anti-pattern.
- Bus-number mapping (all three skills) → script; reference; anti-pattern.
- Optimization formulation, generator limits, copper-plate balance, "use nodal balance for
  DC-OPF" → script (`network_constrained` flag); `scope.network_constrained`; anti-pattern.
- Reserve co-optimization (Rg ≥ 0, ≤ reserve_capacity, Pg+Rg ≤ Pmax, ΣRg ≥ R) → script;
  `scope.co_optimize_reserves`; anti-pattern; checks.
- Operating margin formula and meaning → script; reference.
- Dispatch output format, totals, 2-dp rounding, cost = objective value → script report;
  `assets/deliver.md`.
- CLARABEL; OSQP may fail → script solver order; anti-pattern; reference.
- DC approximations, B matrix, power-balance equation, slack bus, line flow, loading %,
  branch susceptances (X=0 → 0), line-limit constraints → script; reference.
- PGLib-OPF provenance, large-file warning (json.load, quick summary, wc/du) → reference;
  anti-pattern; `scope.network_path` description.
- Bus types table, per-unit conversions, load_network fields, reserve data table,
  get_generators_at_bus, find_slack_bus, get_branch_info, total_load → reference + script.
- cost-functions.md (polynomial, piecewise linear, marginal cost, typical values) →
  `references/cost-functions.md` (verbatim copy); piecewise-linear costs supported in script.
- build_b_matrix.py `build_susceptance_matrix`, `calculate_line_flows` → script (sparse
  equivalent; each line's from/to/flow/limit/loading appears in `most_loaded_lines` and `binding_lines`).

## Deliberate drops

- dc-power-flow's description mentions "sensitivity analysis" (and "contingency analysis" in
  the intro). The source gives no procedure for either, so there is nothing to compile; the agent
  can derive PTDFs from the reference's B-matrix material if a task asks.
- `build_b_matrix.py` `__main__` block (prints matrix size, non-zero count, symmetry) is a demo
  diagnostic and is not needed by the workflow.
- Generic prose ("Economic dispatch minimizes total generation cost…", "DC power flow is a
  linearized approximation…") is background the agent already knows.
- The source's full per-line flow list is not put into the state (4582 rows); top-N, binding
  and overloaded lines are. The agent can recompute any line from the reference formulas.
