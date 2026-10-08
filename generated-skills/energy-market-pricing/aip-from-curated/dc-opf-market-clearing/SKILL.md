---
name: dc-opf-market-clearing
description: "DC optimal power flow market clearing on MATPOWER/PGLib network.json files: economic dispatch with reserve co-optimization, locational marginal prices (LMPs) and reserve clearing price from duals, binding transmission lines, operating margin, and counterfactual price-impact analysis (e.g. raising a line's thermal limit by 20%: cost reduction, LMP changes, congestion relief). Use for energy market pricing, nodal prices, congestion, or DC-OPF tasks on bus/gen/branch/gencost data."
metadata:
  aip-version: "0.5a1"
  version: "1.0"
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
  Clear a power-system energy market on a MATPOWER/PGLib network.json with a DC optimal power
  flow co-optimizing energy and operating reserves, extract locational marginal prices (LMPs) and
  the reserve clearing price from constraint duals, find binding transmission lines, and quantify
  the impact of a counterfactual (e.g. a line rating raised 20%) on cost, LMPs, and congestion.
  Adds a tested sparse cvxpy/CLARABEL model that bootstraps its own dependencies, the correct dual
  sign and scale for LMPs (checked by finite difference), and the report mapping.

trigger_when:
  - A task asks for LMPs, nodal prices, reserve market clearing price, or binding lines from a network.json in MATPOWER format.
  - A task asks for DC-OPF or economic dispatch with reserve co-optimization (reserve_capacity, reserve_requirement).
  - A task asks what happens to cost, prices, or congestion if a transmission line limit, a bus load, or the reserve requirement changes (counterfactual or price impact analysis).
  - Power-flow or market-pricing work on PGLib-OPF style bus/gen/branch/gencost arrays.

do_not_use_when:
  - The task needs AC power flow, voltage magnitudes, reactive power, or losses (the DC model ignores them).
  - The task needs unit commitment (start-up/shut-down decisions over time) or multi-period dispatch.
  - The network data is not MATPOWER-style bus/gen/branch/gencost arrays.

steps:
  - name: parse-request
    kind: client_task
    description: Extract the network path, output path, report format, and counterfactual changes from the request.
    inputs:
      - name: task_request
        type: string
        description: The task's instructions, verbatim, including any required output schema.
    template: assets/parse_request.md
    references:
      - path: references/matpower-network-format.md
        description: Column layout of bus/gen/branch/gencost and reserve fields. Load only if the request refers to columns or fields by name and you need to map them.
    inputs_to: inspect-network

  - name: inspect-network
    kind: execution
    description: Parse network.json with a JSON parser, summarize it, flag data problems, and resolve each counterfactual target (e.g. the branch rows for a line).
    inputs:
      - name: network_path
        type: string
        description: Path to the MATPOWER-style network JSON.
      - name: counterfactual
        type: object
        description: '{"enabled": bool, "modifications": [...]} as produced by parse-request.'
      - name: results_path
        type: string
        description: Scratch path for the solver's full results (not the report path).
      - name: output_path
        type: string
        description: Where the final report must be written.
      - name: report_requirements
        type: string
        description: The request's required output schema, or "none specified".
    script: scripts/inspect_network.py
    inputs_to: inputs-gate

  - name: inputs-gate
    kind: router
    description: Solve when the inputs check out; otherwise repair them first.
    branch_on: inputs_ok
    branches:
      "true": solve-market
      "false": fix-inputs

  - name: fix-inputs
    kind: client_task
    description: Repair the network path or malformed counterfactual modifications reported by the inspector.
    inputs:
      - name: issues
        type: list[*]
      - name: network_path
        type: string
      - name: counterfactual
        type: object
      - name: task_request
        type: string
    template: assets/fix_inputs.md
    inputs_to: solve-market

  - name: solve-market
    kind: execution
    description: >
      Solve the base DC-OPF with reserves (and the counterfactual if enabled) with cvxpy/CLARABEL,
      extract LMPs (= -dual of the MW nodal balance) and the reserve MCP, flag lines >= 99% loaded,
      finite-difference check the prices, compute impact, and write full results plus a report draft.
      Creates its own venv with numpy/scipy/cvxpy on first run if the interpreter lacks them.
    inputs:
      - name: network_path
        type: string
      - name: results_path
        type: string
        description: Where to write the full results JSON (not the final report path).
      - name: counterfactual
        type: object
    script: scripts/solve_market.py
    timeout: 1500
    inputs_to: solve-gate

  - name: solve-gate
    kind: router
    description: Write the report after an optimal solve; diagnose otherwise.
    branch_on: solve_status
    branches:
      optimal: write-report
      failed: diagnose-failure

  - name: write-report
    kind: client_task
    description: Write the report at the requested path in the requested schema from the solver's files, then sanity-check it.
    inputs:
      - name: solve_summary
        type: object
      - name: results_path
        type: string
      - name: report_draft_path
        type: string
      - name: output_path
        type: string
      - name: report_requirements
        type: string
    template: assets/write_report.md
    assets:
      - assets/report_schema.json
    references:
      - path: references/dcopf-market-method.md
        description: The DC-OPF, reserve, LMP, binding-line and counterfactual definitions the solver uses. Load if the request asks for a quantity not in the draft or results, or uses a definition you need to match.
      - path: references/cost-functions.md
        description: Polynomial and piecewise-linear gencost formats, marginal cost 2*c2*P + c1, typical coefficients. Load if the request asks about generator marginal costs or cost curves.
    inputs_to: end

  - name: diagnose-failure
    kind: client_task
    description: Find why the solve failed (bootstrap, bad input, infeasible, unbounded), re-run if fixable, and report.
    inputs:
      - name: solve_summary
        type: object
      - name: network_path
        type: string
      - name: counterfactual
        type: object
      - name: output_path
        type: string
    template: assets/diagnose_failure.md
    references:
      - path: references/dcopf-market-method.md
        description: Full model statement. Load when checking which constraint set makes the problem infeasible.
      - path: references/matpower-network-format.md
        description: Column layout; load when checking generator status, ratings, or reactances in the raw data.
    inputs_to: end

  - name: end
    kind: end
    description: The report written at output_path plus a plain-text summary of the results or the failure.
    inputs:
      - name: output_path
        type: string
      - name: final_answer
        type: string

anti_patterns:
  - Converting LMPs as dual * baseMVA. For the per-unit balance cvxpy gives LMP = -dual / baseMVA; the script writes the balance in MW and uses LMP = -dual. Prices near 10^5-10^6 $/MWh with mostly negative signs mean this mistake.
  - Indexing buses as number - 1. Bus numbers can be non-contiguous; always map bus number to row index.
  - Reading network.json with sed/head/cat or printing it. Use json.load; the file can be 100K+ lines.
  - Treating negative or very large LMPs behind congested lines as errors and "fixing" them.
  - Relaxing every parallel circuit between two buses when the request names one line; the reference method modifies the first matching branch row (either direction).
  - Writing the final report by retyping numbers from the summary instead of loading the results/draft JSON.
  - Using OSQP for DC-OPF with reserves; it fails on these ill-conditioned problems. Use CLARABEL.
  - Installing packages into the container's system python (blocked by PEP 668 on Ubuntu 24.04); the solver script creates its own venv.
```
