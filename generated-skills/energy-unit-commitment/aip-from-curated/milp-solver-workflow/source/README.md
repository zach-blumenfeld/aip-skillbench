# Source notes — `milp-solver-workflow`

This folder holds the canonical inputs used to compile the AIP skill:

- `SKILL.md` — the curated source skill copied verbatim from
  `vendor/skillsbench/tasks/energy-unit-commitment/environment/skills/milp-solver-workflow/SKILL.md`.
- `procedure.schema.json` — the AIP `procedure` schema this skill validates
  against (bundled so the skill is self-contained).

## Why `procedure`

The source skill is a workflow / execution-graph: ten ordered steps from
parse-and-normalize through write-final-output, with explicit input/output
edges (case → var-map → model → solver-result → report-arrays → validation
→ final report). That maps cleanly onto `procedure.schema.json`. No new
schema needed.

## What became a script

The source skill contains three reusable code patterns embedded as inline
Python: a variable-map allocator, a sparse-row builder, and the HiGHS-via-SciPy
solver call. These are deterministic boilerplate — the agent should not
re-transcribe them every run. They live in `scripts/milp_helpers.py`:

- `VarMap` — `alloc(name, shape, lb, ub, integer)` returns an ndarray of
  column indices; `build()` returns assembled `(c, lb, ub, integrality)`.
- `SparseModel` — `add_row(terms, lo, hi)` accumulates a sparse row;
  `build()` returns a `scipy.optimize.LinearConstraint`.
- `solve_milp(c, model, integrality, lb, ub, time_limit, mip_rel_gap)` —
  wraps `scipy.optimize.milp` with sensible defaults and raises when no
  incumbent is returned.
- `extract(name, x, var_map, round_binary_tol)` — pulls a named block from
  the incumbent and rounds binaries iff within tolerance of 0/1.

`scripts/validation_checks.py` collects independent (input-data-only)
recompute helpers that the validation step composes — balance, capacity,
joint reserve, ramp deliverability, min-up/down, startup/shutdown linking,
renewable bounds, cost recomputation. These are deterministic over
structured inputs and produce a per-family pass/fail with max-violation
magnitudes, which is exactly the artifact the reporting step gates on.

## What stayed prose

Anything that requires the agent to **judge or interpret** the input:

- choosing the cost-curve convention (total-cost breakpoints vs marginal
  segment cost vs heat-rate) — this is data-dependent and the source skill
  even lists multiple conventions side-by-side
- naming and shaping decision variables for the specific task
- writing the actual constraint rows (the *families* are listed; the
  per-task algebra is the agent's job)
- diagnosing infeasibility (which family to relax depends on what the
  model already encodes)

Scripting these would over-restrict the skill — they map loosely-specified
data onto rules, which is the prose-step criterion in the AIP best-practices.

## What was dropped

Nothing. Every piece of guidance from the source SKILL.md is either:

- a step in the `steps:` graph,
- captured in `references/patterns.md`, `references/debugging.md`, or
  `references/reporting.md`, or
- listed under `anti_patterns:`.

The completeness check log lives below.

## Completeness map (source → AIP)

| Source section                  | Mapped to                                                          |
|---------------------------------|--------------------------------------------------------------------|
| 10-step workflow                | `steps[*]` (parse → write-final-output)                            |
| Variable Map Pattern            | `scripts/milp_helpers.py::VarMap` + step `build-variable-map`      |
| Sparse Constraint Pattern       | `scripts/milp_helpers.py::SparseModel` + step `add-constraints-by-family` |
| Sign-Safe Encoding              | `references/patterns.md` § Sign-Safe Encoding                      |
| Match Model Rows To Validation  | `references/patterns.md` § Validation Map + step `validate-independently` |
| Piecewise-Linear Costs          | `references/patterns.md` § Piecewise-Linear Costs                  |
| Open-Source Solver Use          | `scripts/milp_helpers.py::solve_milp` + step `solve-milp`          |
| Extraction And Validation       | Steps `extract-incumbent` + `validate-independently` + `recompute-objective-and-summaries` |
| Debugging Infeasibility         | `references/debugging.md` + scenario "Solver returns no incumbent" + `modes[validate-only]` |
| Repair LPs And Heuristics       | `references/debugging.md` § Repair LPs + `modes[repair-from-fixed-commitment]` |
| Reporting Discipline            | `references/reporting.md` + step `write-final-output` + matching `anti_patterns` |
