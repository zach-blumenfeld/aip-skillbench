---
name: grid-dispatch
description: "Least-cost generator dispatch on MATPOWER/PGLib-OPF power networks (network.json with bus, gen, branch, gencost arrays): DC optimal power flow with B-matrix nodal balance and branch thermal limits, optional operating-reserve co-optimization (reserve_capacity, reserve_requirement, capacity coupling), polynomial or piecewise-linear costs. Outputs generator setpoints and reserves, total cost/load/generation/reserve, line loading percentages and most loaded lines, binding constraints, and operating margin. Use for economic dispatch, DC-OPF, reserve scheduling, or line congestion questions on a given grid file."
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
  Solve a power-system economic dispatch on a MATPOWER/PGLib-OPF network.json: DC optimal
  power flow (nodal balance over the B matrix, thermal line limits) with optional spinning-reserve
  co-optimization, minimizing polynomial or piecewise-linear generator cost. One script parses
  the large file, maps non-contiguous bus numbers, builds the sparse DC model, solves it with
  CLARABEL, and writes the generator dispatch, cost/load/generation/reserve totals, most loaded
  lines, binding constraints, and operating margin, with feasibility checks; the agent then
  fits the report to the task's requested schema.

trigger_when:
  - A task gives a power network file (MATPOWER-style bus/gen/branch/gencost arrays, often network.json) and asks for least-cost generator setpoints.
  - Economic dispatch, DC-OPF, or security-constrained dispatch with line limits is requested.
  - Operating reserves (reserve_capacity, reserve_requirement) must be co-optimized with energy.
  - The task asks for total generation cost, line loading percentages, most loaded or binding lines, or operating margin of a dispatch.

do_not_use_when:
  - AC power flow, voltage, or reactive power results are required (this skill is DC only).
  - Unit commitment over multiple periods (start-up decisions, ramping, time coupling) is required.
  - The network data is not MATPOWER-style (e.g. PSS/E RAW, CIM) and has not been converted.

steps:
  - name: scope
    kind: decision
    description: Decide from the task wording which constraints the dispatch must honor.
    inputs:
      - name: task_request
        type: string
        description: The task statement verbatim, including any required output path and JSON schema.
      - name: network_path
        type: string
        description: Absolute path to the network JSON (e.g. /root/network.json). Inspect it with json.load, never by paging lines.
      - name: output_path
        type: string
        description: Where the script writes its default-format report. Use the task's required path (e.g. /root/report.json) when the task's schema matches the default report (generator_dispatch, totals, most_loaded_lines, operating_margin_MW); otherwise a working path next to it (e.g. /root/dispatch_default.json) that deliver reshapes into the requested file. Empty string to skip writing.
      - name: top_n_lines
        type: integer
        description: How many most-loaded lines the task wants listed; 3 when the task does not say.
    questions:
      co_optimize_reserves:
        type: noul
        instructions: >
          Must the dispatch co-optimize operating reserves? Yes when the task mentions reserves,
          reserve requirement, spinning reserve, reserve_MW, or capacity coupling, or asks for an
          operating margin net of reserves and the network file carries reserve_capacity and
          reserve_requirement. No when the task explicitly says to ignore reserves or never
          mentions them and asks only for an energy dispatch.
        criteria:
          true: Reserves are named in the task or its required output (e.g. a reserve_MW field).
          false: The task wants energy-only dispatch.
      network_constrained:
        type: noul
        instructions: >
          Must the dispatch respect the transmission network (DC power flow nodal balance and
          branch thermal limits / RATE_A)? Yes for DC-OPF, security-constrained or
          network-constrained dispatch, or whenever line loading or congestion is part of the
          answer and the task does not say to ignore the network. No only when the task asks for
          a copper-plate / single-bus / unconstrained economic dispatch (total generation equals
          total load, no line limits); line loadings are then still reported from a DC power flow
          of that dispatch.
        criteria:
          true: Network constraints apply (default for a dispatch "on this network").
          false: The task explicitly wants a copper-plate dispatch that ignores line limits.
    thresholds:
      co_optimize_reserves: 0.2
      network_constrained: 0.3
    inputs_to: solve

  - name: solve
    kind: execution
    description: Parse the network, solve DC-OPF/ED (+reserves) with CLARABEL, write the default report and feasibility checks.
    inputs:
      - name: network_path
        type: string
      - name: output_path
        type: string
      - name: top_n_lines
        type: integer
      - name: co_optimize_reserves
        type: boolean
      - name: network_constrained
        type: boolean
    script: scripts/solve_dispatch.py
    timeout: 900
    inputs_to: by-status

  - name: by-status
    kind: router
    description: Optimal solves go to delivery; infeasible or errored solves go to diagnosis.
    branch_on: solve_status
    branches:
      optimal: deliver
      failed: diagnose

  - name: deliver
    kind: client_task
    description: Fit the solver's report to the task's requested schema and path, sanity-check it, and summarize.
    inputs:
      - name: task_request
        type: string
      - name: solver_status
        type: string
      - name: report_summary
        type: object
        description: Totals, most loaded lines (branch_index, from, to, flow, limit, loading), binding lines (network-constrained only), overloaded lines, operating margin, model flags.
      - name: checks
        type: object
        description: Power-balance residual, limit/coupling violations, reserve shortfall, max loading, recomputed cost.
      - name: report_written_to
        type: string
        description: Absolute path of the default-format report the script wrote ("" if output_path was empty).
      - name: notes
        type: list[*]
    template: assets/deliver.md
    references:
      - path: references/dc-opf-formulation.md
        description: Column indices, bus types, per-unit, DC-OPF and reserve equations, operating-margin and loading formulas, and the script's modelling conventions. Load when reshaping the report, computing a quantity the report lacks, or auditing a number.
      - path: references/cost-functions.md
        description: MATPOWER gencost formats (polynomial and piecewise linear) with worked example, marginal cost formula, typical coefficients. Load when the task asks about costs per unit or marginal cost.
    inputs_to: end

  - name: diagnose
    kind: client_task
    description: Explain why the solve failed, fix input problems and re-run, or report the binding infeasibility.
    inputs:
      - name: task_request
        type: string
      - name: solver_status
        type: string
      - name: solver_errors
        type: list[*]
      - name: diagnostics
        type: object
      - name: notes
        type: list[*]
    template: assets/diagnose.md
    references:
      - path: references/dc-opf-formulation.md
        description: Data layout and constraint set; load to check which constraint (limits, reserves, line ratings) can make the problem infeasible.
    inputs_to: end

  - name: end
    kind: end
    description: The written report path(s) and a summary of the dispatch, or the failure analysis.
    inputs:
      - name: final_answer
        type: string
        description: Output file(s) written plus headline numbers, or what failed and why.

anti_patterns:
  - Reading network.json with sed/head/cat or line by line; it is multi-MB. Use json.load (the script already does).
  - Indexing buses as bus_number - 1; bus numbers can be non-contiguous. Map numbers to positions.
  - Using copper-plate balance (total generation = total load) when the task wants DC-OPF; the network needs nodal balance at every bus plus line limits.
  - Forgetting capacity coupling (output + reserve <= PMAX) or the per-generator reserve_capacity cap when reserves apply.
  - Reading cost coefficients at fixed indices without checking NCOST, or treating P in per-unit inside the cost; costs use MW.
  - Using OSQP for DC-OPF with reserves; it can fail on these ill-conditioned problems. Use CLARABEL (the script uses HiGHS first when every cost is linear, CLARABEL otherwise).
  - Retyping or re-rounding solver numbers by hand when reshaping the report; transform the JSON programmatically.
  - Reporting a dispatch whose checks show a power-balance residual, limit violation, reserve shortfall, or overloaded line under network constraints.
```
