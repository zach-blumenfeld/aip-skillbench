---
name: unit-commitment-operating-rules
description: Use for day-ahead or multi-period unit commitment problems, including thermal on/off schedules, dispatch, startup/shutdown logic, minimum up/down time, ramping, spinning reserve deliverability, renewable curtailment, operating-cost accounting, and independent feasibility checks for power-system operations schedules.
compatibility: Requires Python 3 with numpy on the agent runtime. Solver step typically uses scipy.optimize.milp or another open-source MILP solver.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Operating rulebook for multi-period unit commitment (UC). UC decides
  which thermal generators are online over time, when they start or
  stop, how much they produce, and how much reserve they can physically
  provide. It is harder than hourly economic dispatch because
  startup/shutdown decisions, ramping, minimum up/down time, reserve
  deliverability, initial conditions, and cost curves couple one
  period to the next. This skill supplies (a) the variable conventions
  and constraint families that must hold for any feasible UC schedule
  and (b) an independent validator that recomputes every check the
  grader runs so that "pass" is only ever set after the rules are
  actually satisfied. It is a reusable operating guide, not a complete
  task-specific mathematical model.

trigger_when:
  - Task asks for a day-ahead or multi-period unit commitment schedule.
  - Task involves thermal commitment with reserves, ramping, and minimum up/down time.
  - User mentions UC, commitment, startup/shutdown, spinning reserve, or unit dispatch.
  - Need to independently verify a UC schedule before reporting `pass` on constraint checks.
  - Asked to recompute objective cost, hourly summaries, or violation magnitudes from a schedule.

do_not_use_when:
  - Pure economic dispatch — no commitment, no startup/shutdown decisions, no min up/down.
  - AC or DC network power-flow problems with no on/off variables.
  - Pure production-cost simulation with prescribed schedules and no optimization.
  - Storage-only scheduling (state-of-charge problems) without thermal commitment.

scope_and_approval: >
  Read-only against the input case file (e.g. `/root/network.json`).
  Writes the final report file (e.g. `/root/report.json`). No
  destructive system actions. The `validate-schedule` script reads
  both files and writes a verdict to stdout; pass `--out` to also
  persist the verdict next to the report. The agent SHOULD NOT mark
  any `constraint_check` field as `"pass"` until `validate-schedule`
  returns overall=pass.

steps:
  - name: parse-inputs
    description: >
      Load the case file. Identify the time horizon T, demand[t],
      reserve requirement[t], thermal generators (with pmin, pmax,
      ramp_up_limit, ramp_down_limit, ramp_startup_limit,
      ramp_shutdown_limit, time_up_minimum, time_down_minimum, initial
      power_output_t0, initial unit_on_t0, time_up_t0/time_down_t0,
      must_run flag, piecewise_production cost curve, and startup
      tiers indexed by lag), and renewable generators (per-period
      power_output_minimum / power_output_maximum). Preserve original
      generator names and ordering for the final report. Defer to the
      sibling skill `unit-commitment-data-modeling` for general
      parsing guidance when the source schema is unfamiliar; the
      validator script `scripts/validate_schedule.py` reuses the
      pglib-uc field set as its expected layout.
    outputs:
      - name: case
        type: object
        description: Normalized case with T, demand, reserves, thermal[], renewable[], thermal_names, renewable_names.

  - name: pick-output-convention
    description: >
      Decide whether to model production as actual MW (`production[g,t]`)
      or above-minimum MW (`p_above_min[g,t] = actual_output - pmin[g] * u[g,t]`).
      Both are valid internally; the final report MUST contain ACTUAL
      MW per generator (instruction: "the actual value of thermal
      resource production"). Whichever you choose internally, stick
      with it through ramping, reserve, cost, and reporting --
      mixing conventions silently breaks deliverability and ramp
      checks. The validator works on actual-MW report arrays and
      reconstructs above-min internally.
    inputs:
      - name: case
        type: object
    outputs:
      - name: convention
        type: string
        description: Either "actual_mw" or "above_min". Must be applied consistently downstream.

  - name: formulate-uc-model
    description: >
      Build the MILP. Variables per thermal unit g and period t:
      u[g,t] (commitment, binary), v[g,t] (startup transition, binary),
      w[g,t] (shutdown transition, binary), p[g,t] (production --
      actual MW or above-minimum MW per the chosen convention),
      r[g,t] (scheduled spinning reserve, continuous, nonnegative).
      Renewables get q[i,t] continuous bounded by per-period min/max.
      Apply ALL of the following constraint families; each one
      independently caused failures in skills authored without them:
      (1) Transitions linked to u and initial state:
      `u[g,t] - prev_u == v[g,t] - w[g,t]`, where `prev_u = unit_on_t0`
      at t=0 else `u[g,t-1]`; and `v[g,t] + w[g,t] <= 1`.
      (2) Capacity with offline-zero. Actual-MW form:
      `pmin[g]*u <= production <= pmax[g]*u`. Above-min form:
      `0 <= p_above_min <= (pmax-pmin)*u`. When u=0 both production
      and reserve are zero.
      (3) Joint production+reserve deliverability (HEADROOM ALONE IS NOT
      ENOUGH). With startup capability `startup_reduction = max(pmax-ramp_startup_limit, 0)`
      and pre-shutdown capability `shutdown_reduction = max(pmax-ramp_shutdown_limit, 0)`:
      `p_above_min[g,t] + r[g,t] <= (pmax-pmin)*u[g,t] - startup_reduction*v[g,t]`
      and for t<T-1
      `p_above_min[g,t] + r[g,t] <= (pmax-pmin)*u[g,t] - shutdown_reduction*w[g,t+1]`.
      (4) Ramping with reserve on the up side and INITIAL above-min p0:
      let `p0_above_min = unit_on_t0 * (power_output_t0 - pmin)`,
      `previous = p0_above_min` if t==0 else `p_above_min[g,t-1]`.
      Then `p_above_min[g,t] + r[g,t] - previous <= ramp_up_limit`
      and `previous - p_above_min[g,t] <= ramp_down_limit`.
      (5) Minimum up/down. Initial-window obligations: if `unit_on_t0=1`
      and `time_up_t0 < time_up_minimum`, force u=1 for the first
      `time_up_minimum - time_up_t0` periods; symmetrically for down.
      In-horizon obligations: after every startup at t, u must stay 1
      through `min(T, t + time_up_minimum)`; after every shutdown,
      u must stay 0 through `min(T, t + time_down_minimum)`.
      Implement as sliding-window inequalities tied to v[g,t] and w[g,t].
      (6) Must-run: where `must_run=1`, lock `u[g,t] = 1`.
      (7) System balance for the case's single-zone convention:
      `sum_g actual_production[g,t] + sum_i q[i,t] == demand[t]` and
      `sum_g r[g,t] >= reserves[t]`. Renewables stay in `[pmin[i,t], pmax[i,t]]`;
      if pmin==pmax the renewable is fixed (no curtailment). Do NOT
      count renewable headroom as spinning reserve unless the prompt
      explicitly allows it.
      (8) Objective. Sum, for each (g,t):
        - if u==1: piecewise total-cost interpolation at actual MW
          (the cost curve's MW points equal pmin and pmax at the
          endpoints; the first point's cost represents the online
          minimum-output cost -- do not add a separate no-load cost
          unless the data has one);
        - if v==1: startup tier whose `lag` is the largest not
          exceeding the prior offline duration; ties to the smallest
          lag's cost as a floor.
      Do not invent no-load, reserve, curtailment, shutdown, or ramping
      cost terms that are not in the data.
      See `references/constraints.md` for the verbatim formulation
      patterns and pseudocode that this step is a summary of.
    inputs:
      - name: case
        type: object
      - name: convention
        type: string
    outputs:
      - name: uc_model
        type: object
        description: The compiled MILP (variables, constraint matrix, objective). Format depends on the solver chosen.

  - name: solve-uc
    description: >
      Solve the MILP and capture the solver result. Default to
      `scipy.optimize.milp` for self-contained runs; the sibling skill
      `milp-solver-workflow` covers variable indexing, sparse
      constraints, MIP gap handling, and incumbent extraction for
      richer solver stacks. Set a real time limit and a target MIP
      gap (typical: 2-5% on a 48-period pglib case). Capture
      `solver_status` mapped onto one of {optimal, feasible,
      time_limit_feasible, suboptimal_feasible, heuristic_feasible},
      and `reported_mip_gap` as a finite nonnegative float or null.
    inputs:
      - name: uc_model
        type: object
    outputs:
      - name: solver_solution
        type: object
        description: Solver variable values plus solver_status and reported_mip_gap.

  - name: extract-report-arrays
    description: >
      Translate solver variables into the report schema. Required
      structure (see `references/report-schema.md` for the full
      template): top-level `case_name`, `summary`, `thermal_generators`,
      `renewable_generators`, `hourly_summary`, `constraint_check`.
      Per thermal generator: `name` (verbatim from input),
      `commitment` (int 0/1, length T), `production_MW` (ACTUAL MW
      including pmin contribution when u=1), `reserve_MW`, `startup`,
      `shutdown`. Per renewable: `name`, `production_MW`. Per hour:
      `hour` (1-indexed!), `demand_MW`, `thermal_generation_MW`,
      `renewable_generation_MW`, `reserve_requirement_MW`,
      `scheduled_spinning_reserve_MW`. In `summary`: solver_status,
      objective_cost, reported_mip_gap, time_periods,
      num_thermal_generators, num_renewable_generators, total_startups,
      total_shutdowns, max_demand_balance_violation_MW,
      max_reserve_shortfall_MW. Leave numeric `constraint_check`
      values blank/placeholder until validate-schedule passes -- do
      not write "pass" yet.
    inputs:
      - name: solver_solution
        type: object
      - name: case
        type: object
    outputs:
      - name: report_draft
        type: object
        description: A report.json-shaped dict written to disk for the validator to read.

  - name: validate-schedule
    description: >
      Run the independent validator. It reparses the case, reparses
      the report, and replays every check the grader runs (transition
      logic, must-run, generator limits, reserve deliverability with
      startup AND pre-shutdown capacity reductions, ramping with
      reserve and initial p0, minimum up/down with initial-window
      obligations, demand balance, system reserve, renewable bounds
      and fixed-renewable equality, hourly_summary consistency,
      cost_consistency using piecewise interpolation and startup-tier
      lookup). It also returns recomputed summary fields and recomputed
      hourly_summary rows. The agent MUST copy these recomputed values
      verbatim into the final report's `summary` and `hourly_summary`
      before re-running validation -- this is the single largest source
      of cost_consistency and *_violation_MW failures. Exit code is
      0 only when every check passes.
    script: scripts/validate_schedule.py
    inputs:
      - name: report_draft
        type: object
      - name: case
        type: object
    outputs:
      - name: verdict
        type: object
        description: |
          {
            "overall": "pass" | "fail",
            "schema_errors": [string],
            "parse_errors": [string],
            "constraint_checks": {
              "<check_name>": {"status": "pass" | "fail", "violations": [string]}
            },
            "recomputed": {"summary": {...}, "hourly_summary": [{...}]}
          }

  - name: repair-or-resolve
    description: >
      If verdict.overall is "fail", DO NOT relax tolerances or hard-code
      "pass". Read the first violation under each failing check --
      they name the generator and hour. Map the failure mode onto one
      of the alternatives below and act. Re-run validate-schedule
      after every change. Repeat until overall=pass. If a check
      passes but another regresses, the most common cause is mixing
      actual-MW and above-min conventions partway through extraction
      (see pick-output-convention).
    inputs:
      - name: verdict
        type: object
      - name: uc_model
        type: object
    outputs:
      - name: repaired_solution
        type: object
    one_of:
      - Add a missing constraint family to the model and re-solve (e.g. forgot startup-capacity reserve cap, or initial min-up window).
      - Fix an extraction/conversion bug between solver variables and report arrays (most often above-min -> actual MW, or first-period ramping using p0 incorrectly).
      - Tighten or correct the summary recomputation (use the verdict's `recomputed` values verbatim).
      - Re-tune solver settings (time limit, MIP gap) and re-solve if the issue is suboptimality rather than infeasibility.

  - name: finalize-report
    description: >
      Only after validate-schedule returns overall=pass with the
      latest report.json on disk: set every `constraint_check.*` to
      `"pass"`, confirm `summary.solver_status` is in the accepted
      set, and write the final report.json. Numeric fields in
      `summary` and `hourly_summary` MUST equal the verdict's
      `recomputed` values within tolerance -- the simplest way is to
      copy them straight from the verdict.
    inputs:
      - name: verdict
        type: object
      - name: report_draft
        type: object
    outputs:
      - name: report_path
        type: string
        description: Filesystem path to the final report.json.

modes:
  - name: solve
    body: >
      Full pipeline from `parse-inputs` through `finalize-report`.
      Default mode when the task asks for a UC schedule and a report
      file.
  - name: verify-only
    body: >
      When the agent (or a prior step) has already produced a
      report.json, skip to `validate-schedule` against the existing
      report and the case file. Useful for re-validating after a
      manual edit, or as a sanity check before declaring a previous
      solve complete.

integrations:
  - partner: unit-commitment-data-modeling
    body: >
      Use that sibling skill in `parse-inputs` when the source data
      schema is unfamiliar or non-pglib (CSV, spreadsheet, database
      rows, alternative JSON layouts). It maps UC concepts to
      fields by meaning rather than name.
  - partner: milp-solver-workflow
    body: >
      Use that sibling skill in `formulate-uc-model` and `solve-uc`
      for general MILP authoring patterns -- variable maps, sparse
      constraint construction, segment-based piecewise costs, solver
      limits, gap handling, and rounding rules. This skill specifies
      the UC-specific constraint families; that one specifies how to
      encode them efficiently.

scenarios:
  - need: Day-ahead 48-period UC on a pglib-uc case with thermal + renewables, single-zone demand and reserve.
    context: Input at `/root/network.json` matches the pglib-uc schema. Report must be written to `/root/report.json` with hour labels starting at 1 and actual-MW thermal production.
    action: Run parse-inputs -> pick-output-convention="actual_mw" (any internal convention is fine; the report needs actual MW) -> formulate-uc-model with all 8 constraint families -> solve-uc via scipy.optimize.milp with `mip_rel_gap=0.02` and a real time limit -> extract-report-arrays -> validate-schedule -> copy verdict.recomputed into summary and hourly_summary -> validate-schedule again -> finalize-report.
    outcome: A feasible, economical schedule that passes all 11 constraint_check entries with summary fields recomputed from the arrays.
  - need: A previously written report.json has cost_consistency failing.
    context: The model is otherwise feasible.
    action: Run validate-schedule in verify-only mode. Read its recomputed objective_cost. The mismatch is almost always (a) missing startup-cost tier accounting on transitions, (b) piecewise cost interpolated above-min when the curve is total-cost-at-actual-MW, or (c) the first piecewise cost point treated as a no-load adder instead of online minimum-output cost. Fix the cost recompute in extract-report-arrays and re-run.
    outcome: cost_consistency passes; objective_cost matches recomputed within `max(1e-2, 1e-4 * |cost|)`.
  - need: An offline thermal unit reports nonzero production or nonzero reserve.
    context: Common when capacity bounds are written as `p <= pmax` without multiplying by u, or when reserve is set from headroom without the u multiplier.
    action: In formulate-uc-model, replace `p <= pmax` with `pmin*u <= p <= pmax*u`. Replace `r <= pmax - p` with the joint deliverability cap that includes `u`. Re-solve and re-validate.
    outcome: generator_limits passes; offline units carry zero production and zero reserve.

anti_patterns:
  - Treating UC as independent hourly economic dispatch -- ignores transitions, min up/down, and initial conditions.
  - Counting reserve from offline units or from renewable headroom.
  - Checking only headroom (`r <= pmax - p`) instead of joint deliverability with startup and pre-shutdown capacity reductions.
  - Forgetting initial above-min output `p0_above_min` in the first-period ramping constraint.
  - Forgetting `time_up_t0` / `time_down_t0` in the initial min up/down window.
  - Mixing actual-MW and above-min conventions across the model, the extractor, and the report.
  - Adding a fixed no-load cost when the first piecewise point already represents online minimum-output cost.
  - Trusting a repair LP that silently omits a constraint family (deliverability or initial conditions especially).
  - Hard-coding `constraint_check.*` to `"pass"` before validate-schedule succeeds.
  - Writing `objective_cost` and `max_*_violation_MW` from the solver's bookkeeping instead of recomputing them from the extracted arrays.
```
