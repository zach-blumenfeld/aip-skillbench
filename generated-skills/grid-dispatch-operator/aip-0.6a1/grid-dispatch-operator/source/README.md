# grid-dispatch-operator: provenance and compilation notes

## Provenance

Compiled 2026-10-20 into AIP 0.6a1 from three curated Agent Skills, copied verbatim here:

| Source | Content |
|---|---|
| `power-flow-data/SKILL.md` | MATPOWER/PGLib-OPF data layout, bus types, per-unit, reserve fields, bus-number mapping, branch fields, large-file handling |
| `dc-power-flow/SKILL.md` + `scripts/build_b_matrix.py` | DC approximations, B matrix, slack bus, line flows, loading %, flow limits |
| `economic-dispatch/SKILL.md` + `references/cost-functions.md` | gen/gencost columns, cost polynomial, cvxpy formulation, reserve co-optimization, operating margin, output format, CLARABEL choice; PWL costs, marginal cost, typical values |

`task-instruction.md` is the downstream task statement (report.json contents and shape);
it fixed the report schema and the three constraint families.

Intent: one procedure that takes a MATPOWER `network.json`, solves the least-cost DC-OPF
with spinning-reserve co-optimization, verifies it independently, and writes `report.json`;
or, when no optimal dispatch exists, says why.

## Step kinds

| Step | Kind | Why |
|---|---|---|
| `solve-dispatch` | execution | The whole model is deterministic numeric logic (data parsing, bus mapping, B matrix, QP). One script, `scripts/dispatch.py`, mode `solve`. Uses cvxpy + CLARABEL as the sources prescribe (a maintained solver, not a hand-rolled one), with HIGHS/OSQP/SCS fallbacks. Data validation runs first and returns `failed` with `data_errors` instead of crashing or emitting NaN. |
| `route-on-status` | router | Branches on the solver status: `optimal` → verify; `infeasible`/`failed` → diagnose. |
| `verify-and-write-report` | execution | Same script, mode `verify`. Re-derives angles with an independent sparse solve of the reduced B matrix (the `build_b_matrix.py` approach), recomputes flows/loading, checks every constraint, then writes the report. A failed check exits non-zero so the client stops rather than hand-editing numbers. |
| `diagnose-cause` | decision (choice) | Classifying the infeasibility cause is a judgment over a fixed label set, informed by the scripted `check_*` flags. |
| `explain-infeasibility` | client_task | The operator-facing explanation (and, for congestion, the relaxation experiment) is generated text/analysis. |

Both execution steps share one script: the logic (loading, topology, cost evaluation) is
shared, so splitting would duplicate it.

### Environment

The task container (ubuntu:24.04, `python3` 3.12, `python3-pip`, `python3-venv`) has no
numpy/scipy/cvxpy. `requires` names them truthfully (the client checks them). The script
also bootstraps itself: if the imports fail it creates a venv at
`$GRID_DISPATCH_VENV` (default `~/.cache/grid-dispatch-venv`), pip-installs
`numpy scipy cvxpy clarabel`, and re-execs; an existing ready venv is reused without pip.
The `compatibility` field and the `solve-dispatch` description give the manual install
command (`python3 -m pip install --break-system-packages ...`) for clients whose requires
check stops the run first. Tested: bare Python 3.12 → bootstrap → optimal in ~18 s
first run, ~1.5 s after.

## Design decisions

- **Formulation scaling mirrors the sources** (Pg per-unit, Rg in MW, θ in rad, the same
  constraint set). Reserves are unpriced, so reserve above the requirement (and therefore
  `reserve_MW`/`operating_margin_MW` in the last few MW) is degenerate. With the sources'
  scaling CLARABEL lands on the same point as a direct transcription of the source
  snippets (checked on the task file: cost 2,965,637.91 $/h, reserve 5,934.90 MW, margin
  68,314.04 MW in both). An MW-scaled variant gave a different reserve split (5,939.9 MW),
  which is why the scaling is kept.
- **Report cost** is recomputed from gencost at the dispatch (including c0), not taken
  from the solver objective; the difference is reported in verification.
- **Top-3 lines** rank raw `loading_pct` (stable sort), as the source `calculate_line_flows`
  output implies. On the task file 23 lines bind at 100 %, so which three are listed is a
  tie the solver resolves; the independent re-solve and the solver's own angles agree on
  the same three.
- **Out-of-service** generators (GEN_STATUS 0) are fixed at 0 output/reserve but still
  listed in `generator_dispatch` (ids are row order); out-of-service branches and x = 0
  branches carry no flow. **RATE_A = 0** is unlimited (MATPOWER convention; source gives
  loading 0 %). **Missing reserve fields** mean R = 0 and r̄ = Pmax.
- **Relative paths** resolve against `AIP_WORKDIR` (scripts run from their own folder).

## Completeness check (source → where it lives)

power-flow-data:
- Large-file warning, use `json.load`, quick summary → `solve-dispatch` description, anti_patterns, `references/formulation.md`, template step 2; the summary is `diagnostics` (counts, total load).
- `wc -l`/`du -h` size check → deliberate drop (optional, not needed once json.load is used).
- PGLib-OPF/MATPOWER provenance → `references/formulation.md` header, purpose.
- Bus types table (3 slack, 2 PV, 1 PQ) → `references/formulation.md`; slack logic in script `topology`.
- Per-unit conversions, baseMVA → script (Pg pu × baseMVA), formulation.md, anti_patterns (units).
- `load_network` incl. reserve fields → script `load_network`.
- Reserve data table → formulation.md, script.
- Bus number mapping, gen-to-bus mapping → script `topology`, anti_patterns, step description.
- `get_generators_at_bus` → script connection matrix `Cg`.
- `find_slack_bus` → script (first type-3 bus; missing → data_errors note, first bus used).
- Branch info (R, X, B, rating, status) → script (x, RATE_A, BR_STATUS), formulation.md columns.
- Total load Σ PD → script `prechecks`/`build_report`.

dc-power-flow:
- DC approximations (lossless, flat V, small angles) → formulation.md, step description.
- Non-contiguous bus mapping (case300) → script, anti_patterns.
- B matrix construction, x ≠ 0 guard → script `topology` (vectorized), formulation.md.
- Power balance Pg − Pd = Bθ → script constraint, verification `max_nodal_mismatch_MW`.
- Slack θ = 0 → script constraint and reduced solve in verify.
- Line flow b(θf − θt)·baseMVA, loading % with RATE_A → script `verify`/`build_report`.
- Branch susceptance storage → script `topology` (`b`, `Bf`).
- Flow limits ±rate → script constraints.
- `build_b_matrix.py` (B, susceptances, line flows, symmetry sanity print) → merged into `dispatch.py`; the CLI summary printing is a deliberate drop (diagnostic only).

economic-dispatch:
- Gen indices (GEN_BUS, PMAX, PMIN) → script, formulation.md.
- gencost format, NCOST 3/2/1 handling, highest order first, cost in MW → script `gen_cost_terms`/objective, formulation.md, anti_patterns.
- cvxpy objective and Pmin/Pmax limits → script.
- Copper-plate balance Σ Pg = load, "use nodal balance for DC-OPF" → anti_patterns, formulation.md (nodal balance used).
- Reserve co-optimization (Rg ≥ 0, ≤ r̄, Pg + Rg ≤ Pmax, Σ Rg ≥ R) → script, verify checks, anti_patterns.
- Operating margin Σ(Pmax − Pg − Rg) → script `build_report`, step description.
- Dispatch output format (id i+1, bus, output/reserve/pmax, 2 dp) → script `build_report`, step description.
- Totals (cost, load, generation, reserve) → script; cost recomputed from gencost (design decision above).
- Solver selection CLARABEL, OSQP fragility → script solver order, anti_patterns, formulation.md.

cost-functions.md:
- Polynomial type 2 format, equation, coefficient meanings, worked example → formulation.md.
- Piecewise linear type 1 → script (convex epigraph) and formulation.md.
- Marginal cost 2·c2·P + c1 → formulation.md.
- Typical values table → formulation.md (sanity check for diagnosis).

task-instruction.md:
- Report shape and fields → script `build_report`, `verify-and-write-report` description.
- Three constraint families → model and verification checks.

## Deliberate drops

- `wc -l` / `du -h` file-size commands: optional and superseded by `json.load` summary.
- `build_b_matrix.py` `__main__` printout (matrix size, non-zeros, symmetry): a demo, not part of the workflow.
- Startup/shutdown cost columns (gencost 1–2): single-period dispatch has no commitment decisions; noted in `do_not_use_when`.
- Branch R, line-charging B, TAP, SHIFT, angle limits, reactive power and voltage columns: the DC model in the sources uses b = 1/x only; they are listed in formulation.md for reference but not modelled.
- Bus shunt conductance GS: not part of the sources' DC balance.
