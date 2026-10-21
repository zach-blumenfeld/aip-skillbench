---
name: grid-dispatch-operator
description: Least-cost generator dispatch for a MATPOWER power-network snapshot as a DC optimal power flow co-optimizing energy and spinning reserves (DC nodal power balance, generator Pmin/Pmax, branch RATE_A thermal limits, reserve capacity with Pg + Rg <= Pmax coupling, system reserve requirement). Writes report.json with per-generator output and reserve, total cost/load/generation/reserve, the three most loaded lines, and the operating margin; diagnoses infeasible cases. Use for economic dispatch, DC-OPF, grid dispatch operator, energy market clearing, susceptance matrix, line loading, or reserve co-optimization tasks on network.json.
compatibility: Python 3.10+ with numpy, scipy, cvxpy, clarabel. On a bare python3 the solver script bootstraps a venv (python3-venv + pip, needs PyPI access); otherwise install with python3 -m pip install --break-system-packages numpy scipy cvxpy clarabel.
metadata:
  aip-version: "0.6a1"
  version: "1.0"
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
  Decide generator dispatch for a power-network snapshot in MATPOWER JSON (PGLib-OPF
  style, optionally with reserve_capacity / reserve_requirement): a least-cost DC optimal
  power flow co-optimizing energy and spinning reserves, subject to DC power balance at
  every bus, generator Pmin/Pmax, branch RATE_A thermal limits, per-generator reserve
  caps, the capacity coupling Pg + Rg <= Pmax, and the system reserve requirement. A script
  solves it (cvxpy + CLARABEL), a second pass re-derives the DC flows independently,
  checks every constraint, and writes report.json with per-generator output and reserve,
  totals (cost incl. no-load cost, load, generation, reserve), the three most loaded
  lines, and the operating margin (uncommitted capacity beyond energy and reserves).
  If the problem is infeasible, the run diagnoses why instead of writing a report.

trigger_when:
  - A task gives a network.json in MATPOWER format and asks for generator dispatches, economic dispatch, or a DC-OPF.
  - A grid or energy-market operator task requires DC power balance at each bus, generator and transmission limits, and spinning reserve requirements.
  - A report of dispatch, reserve allocation, total cost, most heavily loaded lines, or remaining operating margin is requested for a power system snapshot.

do_not_use_when:
  - The task asks for an AC power flow or AC-OPF (voltages, reactive power, losses).
  - The network is not MATPOWER-style bus/gen/branch/gencost data.
  - Unit commitment over multiple periods (on/off decisions, start-up costs, ramping) is required.

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - numpy
    - scipy
    - cvxpy
    - clarabel

steps:
  - name: solve-dispatch
    kind: execution
    description: >
      Load the network with json.load (never page a multi-MB network file with sed/head),
      map bus numbers to row indices (bus numbers are non-contiguous; never use
      number - 1), build the DC susceptance model (b = 1/x, lossless, flat voltage, small
      angles, slack bus type 3 at angle 0), and solve the least-cost dispatch with reserve
      co-optimization in cvxpy with CLARABEL (falls back to HIGHS, OSQP, SCS). Costs are
      MATPOWER gencost polynomials in MW, highest order first, including the c0 no-load
      term; piecewise-linear rows are supported. Only in-service generators and branches
      count; RATE_A = 0 means unlimited. Missing reserve fields mean no requirement.
      On a bare python3 (the ubuntu:24.04 task container has no numpy) the script
      bootstraps a venv at ~/.cache/grid-dispatch-venv and pip-installs numpy, scipy,
      cvxpy, clarabel itself; if the requires check stops the run first, install them with
      `python3 -m pip install --break-system-packages numpy scipy cvxpy clarabel` and
      rerun. solve_status is optimal, infeasible, or failed.
    inputs:
      - name: network_path
        type: string
        description: Path to the MATPOWER network JSON, absolute or relative to the run's workdir (in the task container usually /root/network.json).
      - name: report_path
        type: string
        description: Where report.json must be written, absolute or relative to the run's workdir (in the task container usually /root/report.json).
    script: scripts/dispatch.py
    command: ["python", "dispatch.py", "solve"]
    timeout: 900
    outputs:
      - name: solve_status
        type: string
        description: optimal, infeasible, or failed (every solver errored or returned another status).
      - name: dispatch
        type: object
        description: "Pg_MW and Rg_MW lists in generator row order and the solver objective; empty unless optimal."
      - name: diagnostics
        type: object
        description: data_errors (malformed-data findings; when fatal the solve is skipped and only these plus solver fields are present), network counts, load and capacity totals, reserve capability, pre-solve check_* feasibility flags, solver used and attempts, solve time.
    inputs_to: route-on-status

  - name: route-on-status
    kind: router
    description: An optimal dispatch is verified and written; anything else is diagnosed.
    branch_on: solve_status
    branches:
      optimal: verify-and-write-report
      infeasible: diagnose-cause
      failed: diagnose-cause

  - name: verify-and-write-report
    kind: execution
    description: >
      Independently re-solve the DC power flow from the dispatch (reduced B matrix, slack
      removed), compute every branch flow and loading_pct = |flow_MW| / RATE_A x 100, and
      check nodal balance, Pmin, Pg + Rg <= Pmax, Rg <= reserve capacity, total reserve >=
      requirement, and loading <= 100 %. Only if all pass, write report.json: per generator
      id (row order, 1-based), bus, output_MW, reserve_MW, pmax_MW; totals
      cost_dollars_per_hour (sum of gencost at the dispatch, including c0), load_MW,
      generation_MW, reserve_MW; most_loaded_lines (top 3 by loading_pct, from/to bus
      numbers); operating_margin_MW = sum(Pmax - Pg - Rg); all rounded to 2 dp. A failed
      check exits non-zero and writes nothing: stop and report it, never hand-edit numbers.
    inputs:
      - name: network_path
        type: string
      - name: report_path
        type: string
      - name: dispatch
        type: object
    script: scripts/dispatch.py
    command: ["python", "dispatch.py", "verify"]
    timeout: 600
    outputs:
      - name: verification
        type: object
        description: Absolute path of the written report, constraint-check residuals, totals, most loaded lines, and operating margin.
    inputs_to: end

  - name: diagnose-cause
    kind: decision
    description: Classify why the DC-OPF has no optimal dispatch, from the pre-solve checks and solver attempts.
    inputs:
      - name: solve_status
        type: string
      - name: diagnostics
        type: object
    questions:
      infeasibility_cause:
        type: choice
        instructions: >
          Which cause best explains the missing optimal dispatch? Use the check_* flags and
          MW totals in the diagnostics: a false check_* flag names a capacity or reserve
          cause directly. If every check_* flag is true and the status is infeasible, the
          network (thermal limits) is the likely cause. If the status is failed (solver
          errors), it is a solver or data problem.
        criteria:
          generation_capacity: check_load_le_pmax or check_pmin_le_load is false — total Pmax cannot cover load, or total Pmin exceeds it.
          reserve_shortfall: Capacity covers load but check_reserve_capacity_ge_requirement or check_pmax_ge_load_plus_reserve is false.
          network_congestion: All check_* flags are true and the status is infeasible; transmission limits block a feasible flow.
          solver_or_data: The status is failed, diagnostics.data_errors is non-empty (null/non-finite values, missing columns, unknown bus numbers, gencost rows short, no type-3 slack bus), or no generator is in service.
    thresholds:
      infeasibility_cause: 0.5
    inputs_to: explain-infeasibility

  - name: explain-infeasibility
    kind: client_task
    description: Write the operator-facing infeasibility report, confirming congestion or unclear causes by relaxing limits on a copy.
    inputs:
      - name: network_path
        type: string
      - name: solve_status
        type: string
      - name: diagnostics
        type: object
      - name: infeasibility_cause
        type: string
    template: assets/infeasibility.md
    references:
      - path: references/formulation.md
        description: MATPOWER columns, cost formats, the exact DC-OPF-with-reserves model, report field definitions, and the checklist of infeasibility causes. Load it to confirm a cause or explain which constraint binds.
    outputs:
      - name: infeasibility_report
        type: string
        description: The binding constraint family with the MW figures proving it, the relaxation test performed and its result, and the data or operator change that would restore feasibility.
    inputs_to: end

  - name: end
    kind: end
    description: >
      The solve status and diagnostics. When optimal, report.json is at report_path
      (the verification output gives its checks and headline numbers); otherwise the
      infeasibility report explains why no report was written.
    inputs:
      - name: report_path
        type: string
      - name: solve_status
        type: string
      - name: diagnostics
        type: object

anti_patterns:
  - Solving a copper-plate dispatch (sum Pg = sum load) when the task requires DC power balance at each bus.
  - Indexing buses as bus_number - 1 instead of mapping bus numbers to row positions; real cases (case300, PGLib) have non-contiguous numbers.
  - Mixing units — Pg in per-unit against reserves or limits in MW, or evaluating gencost on per-unit power; costs and reserves are in MW.
  - Dropping the c0 no-load term from total cost, or reading gencost coefficients lowest order first.
  - Treating RATE_A = 0 as a zero-capacity line instead of unlimited, or dividing by it for loading_pct.
  - Omitting the capacity coupling Pg + Rg <= Pmax, or allowing reserve above a generator's reserve_capacity.
  - Reading the multi-MB network file line by line with sed, head, or cat instead of json.load.
  - Defaulting to OSQP for this QP; it fails on ill-conditioned DC-OPF-with-reserve problems, CLARABEL does not.
  - Hand-editing or hardcoding report numbers after a failed verification, or writing a report from an infeasible solve.
```
