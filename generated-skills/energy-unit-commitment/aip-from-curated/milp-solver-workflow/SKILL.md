---
name: milp-solver-workflow
description: Use for formulating, solving, debugging, and validating mixed-integer linear optimization models with open-source solvers, including variable indexing, sparse constraints, linearized costs, solver limits, MIP gaps, incumbent extraction, numerical tolerances, and deterministic output reporting.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.11+, numpy, and scipy >= 1.11 (HiGHS-backed `scipy.optimize.milp`). No proprietary solvers required.
---

```yaml
purpose: >
  Workflow and implementation guide for mixed-integer linear programs:
  binary/integer decisions, linear constraints, linear or piecewise-linear
  objectives. Covers variable indexing, sparse constraint assembly,
  sign-safe row encoding, linearized/piecewise-linear costs, open-source
  solver limits and MIP gaps, incumbent extraction, numerical tolerances,
  and deterministic post-solve reporting. The bundled helpers encode the
  variable map, the sparse-row builder, the HiGHS invocation, and the
  family-by-family independent validator so the agent runs the same
  discipline a careful modeller would. This is a workflow guide, not a
  complete formulation for any specific problem — the prompt's data
  determines which constraint families apply.

trigger_when:
  - Problem has binary or integer decisions, linear constraints, and a linear or piecewise-linear objective.
  - Time-expanded scheduling models with many repeated `(resource, period)` constraints — unit commitment, lot-sizing, network flow over a horizon, assignment-with-coverage.
  - Need to assemble a MILP from already-normalized input data.
  - Need to debug an infeasible or wrong-answer MILP — encoding suspect, family relaxation, slack diagnostics.
  - Need to validate a candidate optimization solution independently of the solver before reporting it.
  - Need to build a fixed-commitment repair LP that covers every feasibility family in the final report.

do_not_use_when:
  - Pure linear programs with no integers — invoke a plain LP solver directly.
  - Non-linear or non-convex objectives/constraints — this workflow assumes the problem is linearizable.
  - Toy instances where a direct simulation or enumeration is cheaper than building a MILP.
  - The task is purely about parsing input data — use a parsing skill (e.g. `unit-commitment-data-modeling`) to produce the normalized case first.
  - The task is purely about validating a returned schedule against operating rules and no model needs to be built — use the operating-rules skill.

scope_and_approval: >
  Read-only with respect to input data. The workflow writes only the
  final solution report, and only after `validate_solution.run_all_checks`
  returns `ok = True`. Never write a `"pass"` self-check on the back of a
  solver status alone — the solver only knows about the constraints
  actually encoded, and an encoding bug can fool it. If a repair LP is
  used, it must include every feasibility family judged in the final
  report; rerun the independent validator on the repaired incumbent.

steps:
  - name: parse-and-normalize
    description: >
      Project the prompt's inputs into ordered numpy arrays keyed by
      resource and period. Lock resource ordering and the time axis once
      and keep them through the entire workflow. When a separate parsing
      skill (e.g. `unit-commitment-data-modeling`) is available, run it
      first and consume its normalized `case` object.
    outputs:
      - name: data
        type: object
        description: Dict of named arrays — G, T, resource names, demand, reserve requirement, per-resource bounds, ramp rates, initial conditions, cost curves.

  - name: define-decision-states
    description: >
      Before allocating any variable, list every decision state the model
      needs: status indicators (binaries — commitment), transitions
      (binaries — startup, shutdown), continuous quantities (dispatch,
      reserve, flow, inventory), slacks for soft constraints, piecewise-
      linear segments, and tier indicators. Write the list down and use
      it as the master checklist for both the variable map and the
      validation step.
    depends_on: [parse-and-normalize]
    inputs:
      - name: data
        type: object
    outputs:
      - name: decision_spec
        type: object
        description: Named decision blocks with their indexing dimensions, bounds, and integrality.

  - name: build-variable-map
    description: >
      Allocate every block via the bundled `VariableMap.alloc(name, shape,
      lb, ub, integer)`. The map records offsets, bounds, and integrality
      so callers index variables as `vm["commitment"][g, t]` rather than
      computing offsets by hand. Keep block names mnemonic (commitment,
      startup, shutdown, dispatch, reserve, segment) — they become the
      keys of the post-solve report layout.
    script: scripts/variable_map.py
    depends_on: [define-decision-states]
    inputs:
      - name: decision_spec
        type: object
    outputs:
      - name: var_map
        type: object
        description: VariableMap exposing `n`, per-block index arrays via `vm[name]`, plus `lb`, `ub`, `integrality` for the solver.

  - name: add-constraints
    description: >
      Build the sparse constraint matrix family by family with the
      bundled `ConstraintBuilder.add_row(terms, lo, hi, family)`. Use
      sign-safe encoding: write the natural-form inequality first, move
      every variable term to the LHS, then encode. Cover the families
      the problem actually has — bounds, linking (transition), balance,
      time coupling (ramp, min up/down), capacity, joint reserve
      capacity, ramp deliverability, and cost-curve segment widths.
      `cb.family_summary()` prints row counts per family; verify them
      against expected totals (`G*T` per-resource-per-period; `T`
      system-wide) before solving. See `references/modeling-patterns.md`.
    script: scripts/sparse_constraints.py
    depends_on: [build-variable-map]
    inputs:
      - name: var_map
        type: object
    outputs:
      - name: constraint_system
        type: object
        description: ConstraintBuilder with `rows`, `cols`, `vals`, per-row `lb`, `ub`, and `families` labels for diagnostics.

  - name: solve
    description: >
      Build the cost vector via `vm.cost_vector({block: cost_array})`
      and invoke `solve_milp.solve(...)` with an explicit `time_limit`
      and `mip_rel_gap`. Defaults are 600 seconds and 1% relative gap —
      tighten or loosen per problem budget. The helper returns a
      `SolveResult` with `feasible`, `x`, `objective`, `best_bound`,
      `mip_gap`. A "no incumbent" outcome raises RuntimeError — that is
      not a solution and must surface as an error.
    script: scripts/solve_milp.py
    depends_on: [add-constraints]
    inputs:
      - name: constraint_system
        type: object
      - name: cost_vector
        type: list[float]
        description: Length-`vm.n` cost vector built from per-block cost arrays via `vm.cost_vector(...)`.
    outputs:
      - name: solve_result
        type: object
        description: SolveResult dataclass — status, message, feasible, x, objective, best_bound, mip_gap.

  - name: extract-solution
    description: >
      Reshape the flat incumbent into per-block arrays via
      `vm.report_layout(solve_result.x)`. Verify every binary variable is
      within tolerance of 0 or 1 with
      `variable_map.round_near_binary(...)` before treating it as
      discrete. Convert internal-convention quantities (above-minimum
      dispatch, segment quantities) into the report convention (usually
      actual MW). Preserve resource and period source order. See
      `references/modeling-patterns.md` § Extraction discipline.
    depends_on: [solve]
    inputs:
      - name: solve_result
        type: object
      - name: var_map
        type: object
    outputs:
      - name: report_arrays
        type: object
        description: Report-convention arrays keyed by name — commitment, dispatch, reserve, startup, shutdown, plus problem-specific arrays.

  - name: validate-solution
    description: >
      Run `validate_solution.run_all_checks(...)` reading ONLY the input
      data and the report arrays. Cover every constraint family judged
      by the final report — balance, capacity, ramp, joint reserve
      capacity, ramp deliverability, minimum durations, transition
      linking, cost-curve logic. Supply an `objective_recomputer`
      closure that recomputes the total cost from inputs plus report
      arrays; drift versus `solve_result.objective` is the loudest
      signal that internal-to-report conversion is wrong. Only proceed
      when `validation_report["ok"]` is True.
    script: scripts/validate_solution.py
    depends_on: [extract-solution]
    inputs:
      - name: data
        type: object
      - name: report_arrays
        type: object
      - name: solver_objective
        type: float
    outputs:
      - name: validation_report
        type: object
        description: '{ok, families: {family: {ok, violation_count, violations}}, objective: {recomputed, solver, drift}}.'

  - name: repair-if-needed
    description: >
      Only when `validation_report["ok"]` is False AND the failures are
      localized (one or two families, no balance violation, no missing
      family) try a fixed-commitment repair LP. Fix `commitment`,
      `startup`, `shutdown` to the extracted values and resolve the LP
      over the continuous variables, INCLUDING every feasibility family
      checked in the final report. Rerun `run_all_checks(...)` on the
      repaired arrays. If validation still fails or the failures are
      not localized, do not repair — report the violations and stop.
      See `references/debugging-infeasibility.md` § Repair LPs.
    depends_on: [validate-solution]
    inputs:
      - name: data
        type: object
      - name: report_arrays
        type: object
      - name: validation_report
        type: object
    outputs:
      - name: repaired_arrays
        type: object
        description: Report arrays after a successful repair, or the original arrays unchanged when no repair was attempted.
      - name: final_validation
        type: object

  - name: write-final-output
    description: >
      Only when `final_validation["ok"]` is True, emit the final report.
      Use deterministic ordering and plain numeric values (`int`,
      `float` — never numpy scalars). Keep feasibility (from the
      validator) and proof quality (solver `mip_gap`) as separate
      fields. Render resource and period labels exactly as supplied by
      the prompt. Use `null` (when the schema allows) for fields with
      no reliable value — never a `0` placeholder. See
      `references/reporting.md`.
    depends_on: [repair-if-needed]
    inputs:
      - name: repaired_arrays
        type: object
      - name: final_validation
        type: object
      - name: solve_result
        type: object
    outputs:
      - name: report
        type: object
        description: Final solution report matching the prompt's output schema.

scenarios:
  - need: Build a 24-period unit-commitment MILP with binary commitment/startup/shutdown, continuous dispatch and spinning reserve, ramp limits, min-up/min-down, joint capacity for reserves, and a piecewise-linear production cost.
    context: >
      The normalized case provides G thermal units, hourly demand and
      reserve requirements, per-unit `pmin`, `pmax`, `ramp_up`,
      `ramp_down`, `startup_ramp`, `shutdown_ramp`, `min_up`,
      `min_down`, initial state, and a total-cost breakpoint curve
      per unit. Roughly `2 * G * T` binaries and `~3 * G * T`
      continuous variables; row count dominated by per-(g, t) families
      (`~6 * G * T`) plus `T` system-wide balance rows.
    action: >
      Allocate blocks with `VariableMap.alloc`. Assemble rows with
      `ConstraintBuilder.add_rows_vectorized` for the per-(g, t)
      families and `add_row` for system-wide rows. Confirm
      `cb.family_summary()` matches the expected counts before
      solving. Call `solve(..., time_limit=600, mip_rel_gap=0.01)`.
      `vm.report_layout(result.x)`, run `round_near_binary` on the
      three binary blocks, validate with `run_all_checks` covering
      every family, then write the report.
    outcome: >
      A deterministic incumbent that passes independent validation
      and recomputes to the solver's objective within tolerance, with
      `mip_gap` reported separately from the feasibility verdict.

  - need: Solver returns infeasible on a problem the prompt asserts is solvable.
    context: >
      First suspect is the encoding, not the data. The likely
      culprits are mixing total output with output above minimum,
      applying startup/shutdown ramp limits to the wrong quantity,
      off-by-one in `t`/`t-1`, over-constraining initial up/down
      obligations, enforcing post-horizon obligations, treating cost
      segments as feasibility constraints, or bad Big-M values.
    action: >
      Print `cb.family_summary()`. Relax one family at a time until
      feasibility returns; the first family whose removal restores
      feasibility is the suspect. Add diagnostic slacks to the
      suspect family's rows with a large penalty in the objective and
      inspect non-zero slacks. Walk
      `references/debugging-infeasibility.md` § First suspect the
      model encoding.
    outcome: >
      Either an encoding fix (Big-M tightened, index swapped, segment
      bound dropped) or a confirmed data-side infeasibility surfaced
      with the violating row attached.

  - need: Recomputed objective disagrees with the solver objective by 2.4%.
    context: >
      The model uses above-minimum dispatch but the report convention
      is actual MW. The conversion at extraction added `pmin * u` for
      every committed (g, t), but the cost-curve recomputer is still
      reading `p` as above-minimum.
    action: >
      Pin the production-convention conversion to a single named
      function (`internal_to_report` / `report_to_internal`). The
      objective recomputer must call `report_to_internal` (or be
      written directly against the actual-MW report arrays plus
      breakpoint conversion). Rerun `run_all_checks`.
    outcome: >
      Recomputed objective matches the solver objective within
      `objective_tol`; the report no longer carries a silent
      double-counted minimum-output cost.

anti_patterns:
  - Computing variable offsets by hand (`g * T + t`) instead of using a `VariableMap`. Off-by-one in `t` is the most common silent bug.
  - Writing constraint rows with variables on BOTH sides of the inequality. Move every variable term to the LHS before encoding — sign errors otherwise are nearly impossible to debug.
  - Assembling constraints as a dense matrix on time-expanded models. Memory and solve time both blow up; use `ConstraintBuilder.to_scipy()` to emit a CSR matrix.
  - Trusting the solver's status without independent validation. A "feasible" status only proves feasibility against the encoded constraints — an encoding bug fools it.
  - Writing `"pass"` self-check strings before `run_all_checks(...)["ok"]` is True.
  - Repair LP that omits a feasibility family checked in the final report. The repair returns "feasible" while the final validator rejects.
  - Mixing total output with output above minimum within the same row. Pick one convention at parse time and stay in it.
  - Applying startup/shutdown ramp limits to every transition instead of only when `u[t-1] = 0, u[t] = 1` (or the symmetric shutdown).
  - Enforcing min-up/min-down obligations past the horizon end when the prompt does not extend them.
  - Treating piecewise-linear cost-curve segment upper bounds as feasibility constraints. Segment widths shape the objective, not dispatch feasibility.
  - Choosing Big-M arbitrarily large. Set Big-M to the smallest valid upper bound (`pmax`, `ramp`) — a Big-M of `1e9` destroys the LP relaxation.
  - Rounding binaries that are not within tolerance of 0/1. Use `round_near_binary` so out-of-tolerance values surface as errors rather than silently rounding a fractional LP relaxation.
  - Substituting the incumbent's objective for the best dual bound when reporting MIP gap. They are different quantities; use `null` when no bound is available.
  - Reporting a stale MIP gap from a time-limited run as if it were a proven optimum. Gap and feasibility verdict are separate fields.
  - Returning numpy scalars in the final report. Cast to plain `int`/`float` at the serialization boundary or downstream comparators silently fail.
```
