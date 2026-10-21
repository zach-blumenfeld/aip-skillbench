---
name: unit-commitment-milp
description: Solve day-ahead / multi-period thermal unit commitment (UC) with renewables as a MILP using HiGHS via scipy.optimize.milp, and write a validated JSON schedule report. Handles on/off commitment, startup/shutdown transitions, tiered startup costs by offline duration, piecewise total-cost production curves, min/max output, ramping, startup/shutdown capability, minimum up/down time, initial conditions, must-run units, spinning reserve deliverability, and renewable curtailment bounds. Use for pglib-uc / UnitCommitment.jl style network.json cases (time_periods, demand, reserves, thermal_generators, renewable_generators) or similar structured UC data, when a feasible, economical schedule with actual-MW production, reserve, startups, shutdowns, objective cost, solver status, MIP gap, and constraint checks must be reported.
metadata:
  aip-version: "0.6a1"
---

# AIP runtime — format 0.6a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the one JSON object a run carries. Each step declares the keys it reads as `inputs`; `execution` and `client_task` steps declare the keys they add as `outputs`, and a `decision` adds one key per question.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the procedure's result.

## Execution

The state starts as the start step's `inputs` and flows along `inputs_to`; each step adds its outputs to it. Every key is produced by exactly one step, so keys accumulate and nothing is overwritten. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. A step sees only those keys: give it its declared `inputs` and nothing else from the state. You have the final say at every step.

- **`execution`**: before the first one, check that this machine has everything `requires` names (the interpreter at its minimum version, the packages, the tools); if anything is missing, stop and name all of it. Run `script` from its folder, launched with the step's `command` when it has one and `python <script>` otherwise, with one JSON object on stdin, `{"state": <the step's inputs>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout holding exactly the step's `outputs`; add them to the state. A non-zero exit, or output missing a declared key, fails the step: stop there and report it rather than doing the step by hand.
- **`decision`**: answer each question from the step's inputs, and from the run so far only when the step sets `history: true`. Each answer collapses to one value under its question name and is added to the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the step's inputs, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the step's `outputs`; add them to the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. Those keys are the procedure's result.

```yaml
purpose: >
  Produce a feasible, economical day-ahead unit commitment schedule from a structured UC
  case file and write it as a JSON report. A script parses and profiles the case; a
  decision reads the task statement for modeling conventions (renewable curtailment,
  renewable reserve, post-horizon obligations); a script builds the time-expanded MILP
  (output above minimum internally, actual MW in reports), solves it with HiGHS, polishes
  continuous values with the same model at fixed commitment, and validates the extracted
  arrays independently; a router writes the report only when every check passes,
  otherwise the agent diagnoses the failure and reruns.

trigger_when:
  - A task asks for a unit commitment, day-ahead generation schedule, or thermal commitment and dispatch over many periods.
  - The input is a UC case (JSON, CSV, tables) with demand, reserve, thermal generator limits, ramping, min up/down, initial conditions, startup tiers, piecewise production costs, and renewable availability.
  - A report must list per-generator commitment, actual MW production, reserve, startups, and shutdowns plus solver status, objective cost, and MIP gap.

do_not_use_when:
  - The task requires network power flow, branch limits, contingencies (security-constrained UC), or zonal transmission; this model is single-zone system balance.
  - Storage, hydro cascades, or stochastic scenarios are central; the model has no storage or scenario variables.
  - Only a single-period economic dispatch with fixed commitment is asked for.

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - numpy
    - scipy>=1.9

steps:
  - name: inspect-case
    kind: execution
    description: >
      Load the case with structured JSON parsing, map fields by meaning (alias table in
      scripts/uc_core.py), normalize to ordered arrays keeping source order and names,
      and run parser-level checks (series lengths equal T, finite values, pmin <= pmax,
      renewable min <= max, cost-curve span, startup lags, initial status consistency,
      duplicate IDs, capacity vs peak demand plus reserve). Exits non-zero naming the
      missing field and the available keys when the schema cannot be mapped; then read
      references/uc-formulation.md, add the source's names to the alias lists, and rerun.
      Do not remove or rescale any input data.
    inputs:
      - name: network_path
        type: string
        description: Path to the UC case file (e.g. /root/network.json in the task container).
      - name: report_path
        type: string
        description: Where the final JSON report is written (e.g. /root/report.json); its directory must exist.
      - name: task_statement
        type: string
        description: The task's instructions verbatim; read by the conventions decision.
      - name: time_limit_s
        type: float
        description: HiGHS wall-clock budget in seconds for all solve phases. Default 420; capped at 780 so the solve step (timeout 900 s incl. model build and polish) finishes.
      - name: mip_rel_gap
        type: float
        description: Relative MIP gap at which HiGHS stops as optimal. Default 0.001.
    script: scripts/inspect_case.py
    outputs:
      - name: case_profile
        type: object
        description: Horizon, resource counts, demand/reserve ranges, capacity, must-run units, initial obligations, renewable flexibility, startup tier counts, non-convex cost units, cost-curve convention.
      - name: parse_issues
        type: list[*]
        description: Non-fatal data issues found by the parser checks; empty when clean.
    inputs_to: read-task-conventions

  - name: read-task-conventions
    kind: decision
    description: Read the task statement (and the case profile) for the conventions the model must follow; the task statement is the source of truth.
    inputs:
      - name: task_statement
        type: string
      - name: case_profile
        type: object
    questions:
      renewables_curtailable:
        type: noul
        instructions: >
          May renewable output be scheduled anywhere between its hourly minimum and
          maximum (curtailment allowed)? Yes unless the task says renewable output must
          equal its maximum/forecast or must not be curtailed. Hourly min/max bounds in the
          data with no such statement mean yes; where min equals max the output is fixed
          either way.
        criteria:
          true: The task gives min/max availability or allows curtailment, and does not force full use of renewable maximum.
          false: The task says renewables must produce their full forecast/maximum or forbids curtailment.
      renewable_reserve_allowed:
        type: noul
        instructions: >
          Does the task explicitly allow renewable headroom (maximum minus scheduled output)
          to count toward the spinning reserve requirement? No unless it says so; "reserve
          comes from online thermal units" means no.
      enforce_post_horizon:
        type: noul
        instructions: >
          Does the task explicitly require minimum up/down obligations to be fully satisfied
          beyond the last period (forbidding starts/stops whose minimum time would run past
          the horizon)? No unless it says so; standard practice truncates the windows at the
          horizon end.
    thresholds:
      renewables_curtailable: 0.3
      renewable_reserve_allowed: 0.2
      enforce_post_horizon: 0.2
    inputs_to: solve-and-validate

  - name: solve-and-validate
    kind: execution
    description: >
      Build the sparse time-expanded MILP with a deterministic variable map (u, v, w
      binaries; output above minimum; reserve; cost segments; startup tiers) and every
      constraint family: transition logic from initial status, joint production+reserve
      capacity with startup/shutdown capability, reserve <= ramp-up and only from online
      units, ramp limits including reserve and first-period ramp from initial output,
      minimum up/down windows plus initial obligations, must-run, system demand balance,
      system spinning reserve, renewable bounds, piecewise total-cost segments, and
      tiered startup cost by offline duration. Solve with HiGHS in phases within
      time_limit_s: LP relaxation; LP-guided start (fix binaries integral in the LP); full
      MILP for a quarter of the budget (valid dual bound); then large-neighborhood
      sub-MILPs (quarter-horizon time windows, RINS, unit groups) that only improve the incumbent. The
      gap is reported against the full model's bound. Check binaries are near 0/1 before
      rounding, re-solve continuous values
      at fixed commitment with the same model, convert to actual MW, then validate the
      arrays against the input data only and recompute cost from the curves and tiers.
      Runs up to time_limit_s (capped at 780) plus build and polish; when running the script
      by hand give the command at least 900 s or run it in the background.
    inputs:
      - name: network_path
        type: string
      - name: time_limit_s
        type: float
      - name: mip_rel_gap
        type: float
      - name: renewables_curtailable
        type: boolean
      - name: renewable_reserve_allowed
        type: boolean
      - name: enforce_post_horizon
        type: boolean
    script: scripts/solve_uc.py
    timeout: 900
    outputs:
      - name: schedule_path
        type: string
        description: Temp JSON file holding the extracted schedule and solve info; empty when there is no incumbent.
      - name: solve_summary
        type: object
        description: HiGHS status and message, solver_status label (optimal, time_limit_feasible, suboptimal_feasible, infeasible, no_incumbent), objective, dual bound, reported_mip_gap, model size, polish result, solve seconds, options used.
      - name: validation
        type: object
        description: Per-check pass/fail for all eleven report checks, first violations per failing check, recomputed cost, startups, shutdowns, max balance violation, max reserve shortfall.
      - name: schedule_valid
        type: boolean
        description: True only when an incumbent exists and every independent check passes.
    inputs_to: by-validity

  - name: by-validity
    kind: router
    description: Write the report only for a schedule that passed independent validation; otherwise diagnose and rerun.
    branch_on: schedule_valid
    branches:
      "true": write-report
      "false": diagnose-failure

  - name: write-report
    kind: execution
    description: >
      Re-validate the schedule from file, recompute objective cost and summaries from
      the arrays, and write the report in the required format: case_name
      "unit_commitment_schedule"; summary (solver_status, objective_cost,
      reported_mip_gap as a nonnegative number or null, time_periods, generator counts,
      total startups/shutdowns, max balance violation, max reserve shortfall);
      thermal_generators in input order with input names (commitment, actual-MW
      production_MW, reserve_MW, startup, shutdown); renewable_generators
      (production_MW); hourly_summary with hour labels starting at 1 (demand, thermal
      and renewable generation, reserve requirement, scheduled spinning reserve); and
      constraint_check with the eleven checks set from validation. Reads the file back
      and checks keys, lengths, labels, and finiteness.
    inputs:
      - name: network_path
        type: string
      - name: report_path
        type: string
      - name: schedule_path
        type: string
      - name: renewables_curtailable
        type: boolean
      - name: renewable_reserve_allowed
        type: boolean
      - name: enforce_post_horizon
        type: boolean
    script: scripts/write_report.py
    outputs:
      - name: report_summary
        type: object
        description: The written report's path, summary block, and constraint_check block.
    inputs_to: end

  - name: diagnose-failure
    kind: client_task
    description: No valid schedule; find the cause, rerun or fix, and never hand-write a report.
    inputs:
      - name: solve_summary
        type: object
      - name: validation
        type: object
      - name: parse_issues
        type: list[*]
      - name: time_limit_s
        type: float
      - name: mip_rel_gap
        type: float
    template: assets/diagnose.md
    references:
      - path: references/uc-formulation.md
        description: Field mapping table, model rows mapped to report checks, cost conventions, solver statuses, and the infeasibility debugging checklist. Load for any status other than a plain time-limit/no-incumbent, or when a check fails.
    outputs:
      - name: failure_diagnosis
        type: string
        description: Cause, evidence, and the rerun or fix applied or recommended.
    inputs_to: end

  - name: end
    kind: end
    description: The solve summary and independent validation of the schedule; the report file is written on the valid branch.
    inputs:
      - name: solve_summary
        type: object
      - name: validation
        type: object

anti_patterns:
  - Treating UC as independent hourly dispatch, or modeling contingencies or branch flows the task excludes.
  - Removing, rescaling, or clipping input data to make the model solve.
  - Reporting output above minimum instead of actual MW production.
  - Counting reserve from offline units or from renewable headroom when the task does not allow it.
  - Checking reserve headroom only, without startup/shutdown capability and ramp deliverability.
  - Ignoring initial output in first-period ramping or time already on/off in minimum up/down.
  - Inventing no-load, reserve, curtailment, or shutdown costs; treating the total-cost curve as marginal cost.
  - Writing "pass" constraint checks or a report by hand, or trusting solver status without the independent validation.
  - Running a repair LP that omits any constraint family the report judges.
  - Reporting a MIP gap when none is known instead of null, or a solver status the run did not reach.
```
