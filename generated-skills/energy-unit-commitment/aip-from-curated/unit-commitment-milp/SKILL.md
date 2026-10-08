---
name: unit-commitment-milp
description: Solve day-ahead / multi-period thermal unit commitment (UC) as a MILP with open-source HiGHS (scipy.optimize.milp) and report a validated schedule. Parses pglib-uc / UnitCommitment.jl-style JSON (time_periods, demand, reserves, thermal_generators with piecewise_production and startup tiers, renewable_generators) or maps other UC data into it; models on/off, startup/shutdown, min up/down, initial conditions, must-run, ramping, startup/shutdown capability, spinning-reserve deliverability, renewable curtailment, piecewise-linear and tiered startup costs; independently validates and recomputes cost before writing the report. Use for generator scheduling, commitment/dispatch, reserve, or UC cost-minimization tasks.
compatibility: Python 3 with numpy and scipy >= 1.9 (scipy.optimize.milp / HiGHS). No other packages.
metadata:
  aip-version: "0.5a1"
---

# AIP runtime — format 0.5a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the JSON object a step receives. Each step declares its required keys as `inputs`; extra keys pass through.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the final state's shape.

## Execution

The state is one JSON object. It starts as the start step's `inputs` and flows along `inputs_to`; each step's output is merged over it, so keys accumulate and extra keys pass through untouched. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. You may change the state before any step runs; you have the final say at every step.

- **`execution`**: run `script` with one JSON object on stdin, `{"currentState": <state>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout; merge it over the state.
- **`decision`**: answer each question against the state. Each answer collapses to one value under its question name and is merged over the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the state, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the next step's `inputs`; merge them over the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. That state is the procedure's result.

```yaml
purpose: >
  Produce a feasible, low-cost multi-period unit commitment schedule (thermal on/off, startup/shutdown,
  dispatch MW, spinning reserve, renewable output) and the report the task asks for. Scripts carry the
  whole pglib-uc formulation (above-minimum production, joint production+reserve capability, startup and
  shutdown capability, ramping with reserve deliverability, min up/down with initial history, tiered
  startup costs by prior offline duration, total-cost piecewise curves) solved with HiGHS, then an
  independent validator re-derives every feasibility family and the cost from the extracted arrays.
  The agent judges task conventions, normalizes unfamiliar data, debugs failures, and writes the report.

trigger_when:
  - A task asks for a day-ahead or multi-period unit commitment schedule, generator on/off plan, or commitment plus dispatch and reserves.
  - Input is pglib-uc / UnitCommitment.jl-style JSON (time_periods, demand, reserves, thermal_generators, renewable_generators) or similar generator/load/reserve data.
  - A UC schedule must be checked for feasibility (ramping, min up/down, reserve deliverability) or its operating cost recomputed.

do_not_use_when:
  - Single-period economic dispatch with no commitment decisions (an LP suffices).
  - Network-constrained OPF / AC power flow, or storage/hydro scheduling the data does not contain, unless you extend the model first (see references/uc-model.md).

steps:
  - name: inspect-data
    kind: execution
    description: Load the case, summarize its schema, and run parser-level checks (lengths, limits, initial status/output, tiers, cost curves, capacity adequacy).
    inputs:
      - name: task_instructions
        type: string
        description: The task prompt verbatim, including any output path, report schema, and solver limits.
      - name: data_path
        type: string
        description: Absolute path to the case file named by the task (e.g. /root/network.json).
      - name: solution_path
        type: string
        description: Absolute working path for the internal solution JSON, outside the skill folder and not the final report path (e.g. /tmp/uc_solution.json).
      - name: time_limit_s
        type: float
        description: Solver limit from the task; if none is given use 300 (keep <= 1500). If the task caps total wall-clock time, leave ~10 s for model build and validation.
      - name: mip_rel_gap
        type: float
        description: Relative MIP gap from the task; if none is given use 0.001. A time-limited incumbent is still reported.
    script: scripts/inspect_data.py
    inputs_to: data-ok

  - name: data-ok
    kind: router
    description: Canonical, clean data goes to modeling; anything else is normalized first.
    branch_on: data_ready
    branches:
      "true": conventions
      "false": normalize-data

  - name: normalize-data
    kind: client_task
    description: Map the source fields into the canonical case schema by meaning, write the normalized file, and point data_path at it.
    inputs:
      - name: data_path
        type: string
      - name: data_errors
        type: list[*]
      - name: data_warnings
        type: list[*]
      - name: schema_summary
        type: object
    template: assets/normalize.md
    references:
      - path: references/uc-model.md
        description: Canonical schema field meanings, units and conventions, and how each field enters the model. Load when a source field's meaning is unclear.
    inputs_to: inspect-data

  - name: conventions
    kind: decision
    description: Read the task's modeling conventions that change the formulation.
    inputs:
      - name: task_instructions
        type: string
      - name: schema_summary
        type: object
    questions:
      post_horizon_min_updown:
        type: noul
        instructions: Does the task explicitly require minimum up/down obligations that would extend past the last period to be honored (i.e. no start or stop late enough that its full min up/down window cannot complete inside the horizon)?
        criteria:
          true: The prompt says obligations must be satisfied beyond/at the horizon end, or forbids starts/stops whose minimum duration does not fit.
          false: The prompt is silent or says windows are truncated at the horizon end (the usual convention).
      renewable_reserve_allowed:
        type: noul
        instructions: Does the task explicitly allow renewable headroom (max minus output) to count toward the spinning reserve requirement?
        criteria:
          true: Explicit permission for renewables/curtailed capacity to provide reserve.
          false: Silent, or reserve is described as coming from online thermal units.
      renewables_must_use_max:
        type: noul
        instructions: Does the task forbid curtailment, i.e. require renewable output to equal its per-period maximum? Answer what the prompt says; if schema_summary.periods_requiring_curtailment is non-empty, true will be infeasible and the debug step handles the conflict.
        criteria:
          true: The prompt says renewables must be fully used / no curtailment / output fixed at forecast.
          false: Silent or curtailment allowed; output may lie anywhere in [min, max] (min == max already fixes a period).
      enforce_shutdown_capability:
        type: noul
        instructions: Should the shutdown capability rule apply (in the period before a shutdown, output plus reserve <= ramp_shutdown_limit; a unit online at t0 can shut down in the first period only if power_output_t0 <= ramp_shutdown_limit)?
        criteria:
          true: The data has ramp_shutdown_limit and the prompt does not exclude it (default).
          false: The prompt explicitly says to ignore shutdown ramp limits, or the data has no shutdown capability field.
    thresholds:
      post_horizon_min_updown: 0.3
      renewable_reserve_allowed: 0.3
      renewables_must_use_max: 0.3
      enforce_shutdown_capability: 0.3
    inputs_to: solve

  - name: solve
    kind: execution
    description: Build the sparse MILP, solve with HiGHS within the limits, round near-integral binaries, convert to actual MW, and write the solution file.
    inputs:
      - name: data_path
        type: string
      - name: solution_path
        type: string
      - name: time_limit_s
        type: float
      - name: mip_rel_gap
        type: float
      - name: post_horizon_min_updown
        type: boolean
      - name: renewable_reserve_allowed
        type: boolean
      - name: renewables_must_use_max
        type: boolean
      - name: enforce_shutdown_capability
        type: boolean
    script: scripts/solve_uc.py
    timeout: 1800
    inputs_to: solved

  - name: solved
    kind: router
    description: Only a solve with an incumbent is validated; no incumbent is not a solution.
    branch_on: solve_status
    branches:
      optimal: validate
      feasible_limit: validate
      no_incumbent: debug
      infeasible: debug
      non_integral: debug
      data_error: debug

  - name: validate
    kind: execution
    description: Re-derive every feasibility family from the extracted arrays and input data only, recompute cost from the curves and startup tiers, and record checks in the solution file.
    inputs:
      - name: data_path
        type: string
      - name: solution_path
        type: string
      - name: solve_status
        type: string
    script: scripts/validate_uc.py
    inputs_to: valid

  - name: valid
    kind: router
    description: A failed check means a modeling or conversion bug; never report it.
    branch_on: validation_passed
    branches:
      "true": write-report
      "false": debug

  - name: debug
    kind: client_task
    description: Diagnose the failed solve or validation, fix the model, data mapping, conventions, or limits, and re-solve.
    inputs:
      - name: solve_status
        type: string
      - name: solve_info
        type: object
      - name: data_path
        type: string
      - name: solution_path
        type: string
    template: assets/debug.md
    references:
      - path: references/uc-model.md
        description: Row-by-row formulation with the matching validation check for each family, sign-safe encoding, and MILP extension patterns. Load before editing solve_uc.py.
    inputs_to: solve

  - name: write-report
    kind: client_task
    description: Write the task's required output from the validated solution file, in the task's exact schema, path, units, and period labeling.
    inputs:
      - name: task_instructions
        type: string
      - name: solution_path
        type: string
      - name: checks
        type: object
      - name: recomputed_cost
        type: object
      - name: solve_info
        type: object
    template: assets/write_report.md
    inputs_to: report-check

  - name: report-check
    kind: decision
    description: Confirm the written report matches the task's required schema and the validated numbers.
    inputs:
      - name: task_instructions
        type: string
      - name: report_path
        type: string
        description: Path of the output file; comma-separated paths when the task asks for several files.
      - name: report_self_check
        type: string
    questions:
      report_ok:
        type: noul
        instructions: Does every report file exist at the path the task requires, with exactly the required keys/columns, resource IDs and period count, units, and values copied from the validated solution (costs from recomputed_cost, check fields "pass" only because validation passed, gap null when no reliable bound)?
        criteria:
          true: Every required field is present with correct names, shape, ordering, and values; nothing invented.
          false: Any required field missing, renamed, mis-shaped, rounded so balance breaks, or filled with placeholders.
    thresholds:
      report_ok: 0.2
    inputs_to: report-done

  - name: report-done
    kind: router
    description: Fix the report until it matches the spec.
    branch_on: report_ok
    branches:
      "true": end
      "false": write-report

  - name: end
    kind: end
    description: The validated schedule written in the task's format, with its recomputed cost.
    inputs:
      - name: report_path
        type: string
      - name: solution_path
        type: string
      - name: validation_passed
        type: boolean
      - name: recomputed_cost
        type: object

anti_patterns:
  - Treating UC as independent hourly dispatch; commitment, ramping, min up/down, and initial conditions couple periods.
  - Mixing actual MW with output-above-minimum in ramping, reserve, cost, or the report (solution file dispatch is actual MW; ramp/reserve rules use above-minimum).
  - Counting reserve from offline units or renewable headroom, or checking reserve against pmax headroom only and forgetting startup/shutdown capability and ramp-up deliverability.
  - Ignoring power_output_t0 in first-period ramping, or time_up_t0/time_down_t0 in initial minimum up/down obligations.
  - Inventing no-load, shutdown, reserve, curtailment, or ramping costs; the first cost-curve point at pmin already is the online minimum-output cost.
  - Treating the startup tier list as sorted or picking the coldest tier; the tier is the largest lag not exceeding the periods offline before the start.
  - Hard-coding a familiar schema or a familiar answer instead of computing from the file given; losing source order of resources or periods.
  - Repairing with a fixed-commitment LP that omits ramp, reserve, startup/shutdown, or min up/down rows; re-solve the full model and re-validate instead.
  - Writing "pass" checks, a status, or a gap from solver self-report without the validator; reporting a run with no incumbent.
  - Putting test inputs, normalized data, or solution files inside the skill folder.
```
