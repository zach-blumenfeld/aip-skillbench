# Source notes — milp-solver-workflow → AIP

This folder bundles the canonical source used to author the AIP version
of `milp-solver-workflow`:

- `original-SKILL.md` — verbatim copy of the curated source skill at
  `vendor/skillsbench/tasks/energy-unit-commitment/environment/skills/milp-solver-workflow/SKILL.md`.
- `procedure.schema.json` — the AIP schema the AIP `SKILL.md` validates
  against (`procedure` family, v0.3a2). Bundled locally per AIP best
  practice so the skill is self-contained.

## Schema choice

`procedure` is the right fit. The source is a stepwise modeling
workflow — parse, define decision states, build a variable map, add
constraints by family, solve, extract, validate, write the report. That
maps cleanly onto the `procedure` schema's required `purpose` /
`trigger_when` / `steps` fields, with the conditional logic (variable
allocation, sparse row assembly, solver invocation, family-by-family
validation) pushed into `scripts/`.

No new schema was authored.

## Logic encoded as scripts

The source guide contains four pieces of executable logic that AIP
best practice requires to live in scripts rather than prose:

1. **Variable map.** The `alloc()` pattern with offset tracking, lb/ub
   bookkeeping, integrality flags, cost-vector assembly, and incumbent
   reshaping. Lives in `scripts/variable_map.py` as
   `VariableMap.alloc/cost_vector/report_layout` plus the
   `round_near_binary` post-solve check.
2. **Sparse constraint assembly.** The `add_row()` pattern with
   sign-safe row encoding, family labels for diagnostics, and a
   vectorized `add_rows_vectorized` for `(g, t)`-shaped families.
   Lives in `scripts/sparse_constraints.py` as
   `ConstraintBuilder.add_row/add_rows_vectorized/to_scipy` plus the
   `largest_violations` per-family diagnostic.
3. **Solver invocation.** HiGHS via `scipy.optimize.milp` with
   explicit `time_limit`, `mip_rel_gap`, silenced output, structured
   `SolveResult` return (`feasible`, `x`, `objective`, `best_bound`,
   `mip_gap`), and the "no incumbent = RuntimeError" discipline. Lives
   in `scripts/solve_milp.py`.
4. **Independent validation.** Per-family checks for binary
   integrality, balance, capacity, ramp, transitions, minimum
   durations, and joint reserve capacity, plus an aggregator that
   recomputes the objective from inputs and report arrays and compares
   to the solver objective. Lives in `scripts/validate_solution.py`.

The other source content — the workflow narrative, the modeling-row
to validation mapping, the piecewise-linear cost classification, the
infeasibility suspect list, the repair-LP guidance, and the reporting
discipline — is reference material the agent consults at point of use,
not executable logic. It lives across three reference files:

- `references/modeling-patterns.md` — variable map, sparse rows,
  sign-safe encoding, model-row to validator mapping, piecewise-linear
  costs, open-source solver use, extraction discipline.
- `references/debugging-infeasibility.md` — suspect list, debug
  stages, repair LP discipline, data-side infeasibility markers.
- `references/reporting.md` — determinism, feasibility-vs-proof-quality
  separation, self-check string discipline, MUST/MUST-NOT contents.

## Completeness audit (source → AIP)

Walked `original-SKILL.md` line by line. Classification:

- **Mapped** — the ten-step workflow (`steps`), variable map pattern
  (`scripts/variable_map.py` + `references/modeling-patterns.md`),
  sparse constraint pattern (`scripts/sparse_constraints.py` +
  `references/modeling-patterns.md`), sign-safe encoding
  (`references/modeling-patterns.md` and enforced by the
  `ConstraintBuilder.add_row(terms, lo, hi)` signature),
  model-rows-to-validation table (`references/modeling-patterns.md`
  and `scripts/validate_solution.py` matched to that table),
  piecewise-linear costs (`references/modeling-patterns.md`),
  open-source solver use (`scripts/solve_milp.py` +
  `references/modeling-patterns.md`), extraction and validation
  discipline (`scripts/validate_solution.py` +
  `references/modeling-patterns.md`), debugging infeasibility
  (`references/debugging-infeasibility.md`), repair LP discipline
  (`references/debugging-infeasibility.md`), reporting discipline
  (`references/reporting.md`), and the common-mistakes set
  (`anti_patterns`).
- **Schema gap** — none. `procedure` covers every section.
- **Body drop** — none.
- **Deliberate drop** — none. Inline code blocks from the original
  became helper functions in `scripts/` (preferred per AIP best
  practice) with the explanation moved alongside the helper.

## Name lock

The source skill's frontmatter name `milp-solver-workflow` is preserved
exactly in the AIP `SKILL.md`. The task's mounted skill name must match
this folder name, so it is not negotiable.
