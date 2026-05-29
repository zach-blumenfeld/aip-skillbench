---
name: milp-solver-workflow
description: Use for formulating, solving, debugging, and validating mixed-integer linear optimization models with open-source solvers, including variable indexing, sparse constraints, linearized costs, solver limits, MIP gaps, incumbent extraction, numerical tolerances, and deterministic output reporting.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.10+, numpy, scipy (HiGHS bundled).
---

```yaml
purpose: >
  Formulate, solve, debug, and validate mixed-integer linear programs (MILPs)
  for binary/integer decisions over time-expanded resources. Encodes the
  engineering patterns that distinguish a feasible-and-correct report from one
  the solver "claims" is optimal but an independent validator rejects:
  deterministic variable maps, sparse sign-safe constraint rows, model-row to
  validation-check parity, piecewise-linear cost conventions, staged
  infeasibility diagnosis, and reporting discipline that never trusts solver
  status alone.

trigger_when:
  - User asks for a unit-commitment, scheduling, dispatch, or assignment plan
    with binary on/off decisions, time-coupled limits, and a linear or
    piecewise-linear cost.
  - The problem has many repeated resource-period constraints — balance,
    capacity, ramping, minimum up/down, startup/shutdown logic.
  - Extracting a solution from a MILP solver and need to convert internal
    variables to a report convention plus run independent validation.
  - Solver returns "no incumbent" or infeasible and a staged-relaxation debug
    path is needed.

do_not_use_when:
  - The problem is nonlinear / nonconvex without a linearization plan — use a
    nonlinear solver workflow instead.
  - The problem has no integer variables — a pure LP workflow has less overhead.
  - Only need to score or validate an externally-produced schedule — skip the
    modeling steps and enter at `validate-independently`.

scope_and_approval: >
  Writes one final output file per run (the report). No other side effects.
  No network calls. Solver time limit defaults to 600s; raise with the user
  before exceeding 1800s on a fresh case. Do not write the final output until
  `validate-independently` passes every family.

steps:
  - name: parse-and-normalize-data
    description: >
      Read the input case and project every per-resource, per-period value
      into ordered numpy arrays (G generators × T periods). Sort each resource
      list into a deterministic order and reuse that ordering for every
      downstream array — it is also the report's emission order.
    inputs:
      - { name: input-case-path, type: string }
    outputs:
      - { name: case, type: object, description: "Arrays + metadata: generator order, T, demand, reserve requirement, per-resource params, initial conditions." }

  - name: define-decision-states
    description: >
      Before writing any code, list every decision the model will represent:
      status (commitment), transitions (startup/shutdown), continuous
      quantities (production, reserve), slacks (demand-violation,
      reserve-shortfall), cost-curve segments, and tiers. Decide each domain
      (binary, continuous ≥0, bounded). Cross-reference the report schema so
      the conversion step has no surprise gaps.
    inputs:
      - { name: case, type: object }
      - { name: report-schema, type: object, description: "Field list the final report must populate." }
    outputs:
      - { name: decision-states, type: "list[object]" }

  - name: build-variable-map
    description: >
      Allocate a deterministic variable map via `VarMap.alloc` — one named
      block per decision, shaped to fit the problem, with lb/ub/integrality
      recorded inline. Keep ownership obvious in the block name (type +
      resource + period + optional segment/tier).
    script: scripts/milp_helpers.py
    inputs:
      - { name: decision-states, type: "list[object]" }
    outputs:
      - { name: var-map, type: object, description: "VarMap with offsets[name]→ndarray of column indices, plus assembled c/lb/ub/integrality on build()." }

  - name: add-constraints-by-family
    description: >
      Build constraints family-by-family with `SparseModel.add_row`: bounds,
      linking (startup/shutdown ↔ commitment transition), balance (demand,
      inventory), time coupling (ramp, min up/down), capacity (joint
      production + reserve), and cost-curve logic. For every row, write the
      intended inequality first (see `references/patterns.md` § Sign-Safe
      Encoding), then move variable terms to the LHS. Hand-test non-obvious
      rows on a tiny case before scaling.
    script: scripts/milp_helpers.py
    inputs:
      - { name: var-map, type: object }
      - { name: case, type: object }
    outputs:
      - { name: model, type: object, description: "Sparse LinearConstraint, lb/ub vectors, integrality, objective coefficients." }

  - name: solve-milp
    description: >
      Solve via HiGHS through SciPy with explicit time limit and MIP gap.
      Capture status, objective, incumbent, and best available bound. A
      `time_limit` status is acceptable iff a feasible incumbent exists; "no
      incumbent" is not a solution — raise and enter `references/debugging.md`.
    script: scripts/milp_helpers.py
    inputs:
      - { name: model, type: object }
      - { name: time-limit-seconds, type: float, description: "Default 600." }
      - { name: mip-rel-gap, type: float, description: "Default 0.01." }
    outputs:
      - { name: solver-result, type: object, description: "status, message, objective, x (incumbent), reported_gap." }

  - name: extract-incumbent
    description: >
      Pull each named block out of `solver-result.x` through the var map.
      `extract()` rounds binaries only when within numerical tolerance (1e-6)
      of 0/1; larger deviations raise — that is a model signal, not a
      rounding question. Convert any internal-unit decisions back into the
      report convention here (e.g., "above minimum" → total output), not
      later.
    script: scripts/milp_helpers.py
    inputs:
      - { name: solver-result, type: object }
      - { name: var-map, type: object }
      - { name: case, type: object }
    outputs:
      - { name: report-arrays, type: object, description: "Per-resource, per-period arrays in REPORT units." }

  - name: validate-independently
    description: >
      Re-check every constraint family the report claims to satisfy, reading
      only the input case and the report-units arrays. Compose the helpers
      in `scripts/validation_checks.py` so the check set MIRRORS the family
      list added in `add-constraints-by-family` — see `references/patterns.md`
      § Validation Map. If any family fails, return to
      `add-constraints-by-family` (or `references/debugging.md`). Do not
      patch the report.
    script: scripts/validation_checks.py
    inputs:
      - { name: case, type: object }
      - { name: report-arrays, type: object }
    outputs:
      - { name: validation-report, type: object, description: "Per-family pass/fail + max violation magnitudes; `all_pass` flag." }

  - name: recompute-objective-and-summaries
    description: >
      Recompute every reportable summary (objective cost, total startups,
      shutdowns, max balance violation, etc.) from the report-units arrays
      plus the input case — never from solver internals. The recomputed
      objective is what is written to the report; a mismatch with
      `solver-result.objective` outside the MIP gap signals a conversion
      bug, not a solver bug.
    script: scripts/validation_checks.py
    inputs:
      - { name: case, type: object }
      - { name: report-arrays, type: object }
      - { name: solver-result, type: object }
    outputs:
      - { name: recomputed-summary, type: object }

  - name: write-final-output
    description: >
      Only after `validation-report.all_pass` is true: emit the report with
      deterministic ordering, plain numeric values, every schema-required
      field populated, and each `constraint_check` flag taken from the
      matching family in `validation-report`. Use `null` for
      `reported_mip_gap` when no reliable bound exists. See
      `references/reporting.md` for status mapping, numeric hygiene, and
      schema discipline.
    inputs:
      - { name: report-arrays, type: object }
      - { name: recomputed-summary, type: object }
      - { name: validation-report, type: object }
      - { name: output-path, type: string }
    outputs:
      - { name: report-path, type: string }

modes:
  - name: full-build
    body: >
      Default. Build the model from scratch, solve, extract, validate, and
      write the report. Skip earlier steps only when a downstream artifact
      already exists from this same run.
  - name: repair-from-fixed-commitment
    body: >
      If a candidate commitment exists but dispatch is infeasible, build a
      fixed-commitment LP that includes EVERY feasibility family the final
      report is judged against — balance, capacity, ramp, reserve
      deliverability, startup/shutdown logic, minimum up/down. A repair LP
      that omits any family produces a report that fails validation. After
      repair, re-run `validate-independently`. See `references/debugging.md`
      § Repair LPs.
  - name: validate-only
    body: >
      Skip modeling and solve. Read an externally-supplied report,
      run `validate-independently`, and surface failures with violation
      magnitudes. Do not modify the report.

search_shortcuts:
  - category: Solver
    body: >
      `scipy.optimize.milp` wraps HiGHS — default. Options:
      `time_limit`, `mip_rel_gap`, `disp`. Result fields used:
      `status`, `message`, `fun`, `x`, `mip_dual_bound`.
  - category: Sparse matrices
    body: >
      `scipy.sparse.csr_matrix((vals, (rows, cols)), shape=(R, N))` — built
      from COO triples accumulated by `SparseModel`. Pass through
      `scipy.optimize.LinearConstraint(A, lb, ub)`.
  - category: Helpers
    body: >
      `scripts/milp_helpers.py`: `VarMap`, `SparseModel`, `solve_milp`,
      `extract`. `scripts/validation_checks.py`: per-family check helpers
      + `assemble_report` + `recompute_thermal_cost`.

scenarios:
  - need: Day-ahead unit-commitment schedule, 48 periods, thermal + renewable mix, system-wide demand and spinning reserve.
    context: >
      Input case has per-thermal cost curves (identify convention via
      `references/patterns.md` § Piecewise-Linear Costs), min/max output,
      ramp limits, min up/down, initial commitment + uptime/downtime.
    action: >
      `parse-and-normalize-data` → `define-decision-states` (commit,
      startup, shutdown, dispatch, reserve, cost segments) →
      `build-variable-map` (alloc each block on `(G_thermal, T)` or
      `(G_renewable, T)`) → `add-constraints-by-family` (transition
      linking, online capacity, joint reserve, ramp, min-up/down, balance,
      reserve adequacy, segment width + production link, renewable
      bounds) → `solve-milp` → `extract-incumbent` (round binaries;
      convert dispatch from internal "above-min" to total MW if needed) →
      `validate-independently` → `recompute-objective-and-summaries` →
      `write-final-output` to `/root/report.json` with constraint_check
      flags from `validation-report`.
    outcome: >
      Report passes the independent verifier because the validation
      family list mirrors the constraint families, the recomputed cost
      matches within MIP gap, and binaries were near-integral before
      rounding.

  - need: Solver returns "no incumbent" / infeasible.
    context: Likely model encoding bug — see `references/debugging.md`.
    action: >
      Relax one family at a time (drop min-up/down, then ramp, then joint
      reserve, then transition linking) and re-solve. The first family
      whose removal restores feasibility is the prime suspect. Print
      shapes against `(G, T)`, hand-test the suspect family with
      `u=1, start=1` and `u=1, start=0` to verify the sign-safe encoding,
      then patch and resume from `add-constraints-by-family`.
    outcome: Bug localized to a single family without blanket-relaxing.

  - need: Solver reports optimal but `validate-independently` flags reserve_deliverability.
    context: >
      The model never added a `p + r ≤ pmax * u` row, or the row used
      the wrong pmax (e.g., the segment-sum instead of physical pmax).
    action: >
      Add (or correct) the joint reserve capacity family in
      `add-constraints-by-family`, re-solve, re-extract, re-validate.
      Do not patch the report — the asymmetry between modeled families
      and validated families is exactly the bug class to fix at the
      source.
    outcome: Reported and validated views agree.

anti_patterns:
  - Trusting solver status or self-reported `"pass"` strings instead of running independent validation against input data plus extracted arrays.
  - Mixing total output with output-above-minimum between rows — pick one internal convention and convert exactly once at `extract-incumbent`.
  - Applying startup or shutdown capability limits to total output instead of the transition quantity.
  - Off-by-one on `t` vs `t-1` in ramp / transition rows; failing to consume the case's `initial_*` fields at t=0.
  - Over-constraining initial obligations — forcing `u==1` for all `t < min_up` instead of only the leftover `min_up - initial_uptime` window.
  - Enforcing post-horizon obligations the prompt did not require.
  - Treating cost-curve segment rows as feasibility constraints (forcing segment activation that the trigger did not require).
  - Choosing arbitrary Big-M; use the tightest physically meaningful bound (typically `pmax`).
  - Validating fewer families than the model encodes (or more) — the asymmetry is where bugs hide.
  - Using a fixed-commitment repair LP that omits ramp, reserve deliverability, startup/shutdown capability, or minimum durations.
  - Reporting a fabricated `reported_mip_gap` (e.g., the configured target instead of a measurement); use `null` instead.
  - Rounding binaries without first checking they are within ~1e-6 of 0/1.
  - Emitting `NaN`, `inf`, `-0.0`, or numpy scalars in the report JSON — coerce to plain `float` / `int` first.
```
