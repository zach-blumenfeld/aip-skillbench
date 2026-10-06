---
name: energy-market-pricing
description: Clear a wholesale energy market on a MATPOWER-format power system by solving a DC-OPF with operating-reserve co-optimization, extracting locational marginal prices (LMPs) and the reserve clearing price from constraint duals, flagging transmission lines at or near their thermal limit, and optionally running a counterfactual that relaxes the most binding line to quantify congestion cost. Use whenever the task asks for nodal electricity prices, generator dispatch and reserves, binding transmission constraints, or congestion / shadow-price impact analysis on a PGLib-OPF-style network.json.
compatibility: Scripts require Python with numpy and cvxpy (CLARABEL solver). The reference Dockerfile under source/ bootstraps Python; the scripts install cvxpy on first invocation if it is missing — see scripts/_dcopf.py for the imports.
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
  Clear a wholesale energy market on a PGLib-OPF-style power network. A
  script solves the DC-OPF with reserve co-optimization and pulls LMPs
  from nodal-balance duals and the reserve MCP from the reserve-requirement
  dual. The client decides whether a counterfactual on the most binding
  line is warranted; if yes, a second script relaxes that line and
  measures the congestion-relief impact. The client then renders a
  market-pricing report.

trigger_when:
  - A request to compute nodal electricity prices (LMPs) on a MATPOWER / PGLib-OPF network.json.
  - A request to find the cheapest generator dispatch meeting load and reserve requirements on a power grid, with or without transmission constraints.
  - A request to identify binding transmission constraints and quantify their congestion cost (shadow price, cost-reduction counterfactual).
  - A request for a wholesale-market clearing report including dispatch, reserves, LMPs, reserve MCP, and congestion diagnostics.

do_not_use_when:
  - The task requires AC power flow (voltage magnitudes, reactive power, line losses) — DC approximation is used here.
  - The task is unit commitment with startup / shutdown decisions — this is a single-period dispatch, not a MILP commitment problem.
  - The network data is in a non-MATPOWER format (RAW, CIM, PSS/E) and no conversion is provided.

steps:
  - name: solve-base
    kind: execution
    description: >
      Load the MATPOWER-format network.json, build the susceptance matrix,
      solve DC-OPF with reserve co-optimization, and return the base-case
      dispatch, LMPs, reserve MCP, line flows, and binding-line list.
    inputs:
      - name: network_path
        type: string
        description: Absolute or working-directory-relative path to the MATPOWER-format network.json file.
    script: scripts/solve_base.py
    inputs_to: evaluate-counterfactual

  - name: evaluate-counterfactual
    kind: decision
    description: >
      Decide whether a counterfactual that relaxes the most binding line
      is warranted. Only meaningful when the base case has at least one
      binding line (loading ≥ 99%).
    inputs:
      - name: base_results
        type: object
        description: >
          The base DC-OPF solve. Includes `binding_lines` (list of lines
          at ≥99% loading) and `cost_dollars_per_hour`.
    questions:
      counterfactual_decision:
        type: choice
        instructions: >
          Should we run a counterfactual that relaxes the most binding
          transmission line and measures the cost / LMP impact?
        criteria:
          run: >
            `base_results.binding_lines` is non-empty — the system is
            congested and quantifying the shadow price of the most
            binding line adds information to the report.
          skip: >
            `base_results.binding_lines` is empty, OR the request
            explicitly asked for base-case pricing only without
            counterfactual analysis.
    thresholds:
      counterfactual_decision: 0.3
    inputs_to: route-counterfactual

  - name: route-counterfactual
    kind: router
    description: Branch on whether the counterfactual was requested.
    branch_on: counterfactual_decision
    branches:
      run: solve-counterfactual
      skip: write-report

  - name: solve-counterfactual
    kind: execution
    description: >
      Pick the binding line with the highest loading percentage, multiply
      its RATE_A by `counterfactual_scale` (default 1.20), re-solve the
      DC-OPF, and compute cost reduction, per-bus LMP deltas, and whether
      congestion on the targeted line was relieved.
    inputs:
      - name: network_path
        type: string
      - name: base_results
        type: object
    script: scripts/solve_counterfactual.py
    inputs_to: write-report

  - name: write-report
    kind: client_task
    description: >
      Render the market-pricing report as markdown from the base solve
      and (if present) the counterfactual results. Use the template as
      the authoring guide and emit the finished markdown under `report`.
    inputs:
      - name: base_results
        type: object
    template: assets/report_template.md
    references:
      - path: references/matpower-format.md
        description: Load only if a bus / gen / branch / gencost column index is unclear while composing the report, or to explain negative LMPs and per-unit vs MW scaling.
      - path: references/dcopf-formulation.md
        description: Load only when a result looks surprising (negative LMPs, counterfactual cost that did not decrease, missing reserve MCP) and the economic / mathematical reasoning needs to be checked.
    inputs_to: end

  - name: end
    kind: end
    description: Final state carries the base DC-OPF results and the rendered market-pricing report. Counterfactual keys are present when the counterfactual branch ran.
    inputs:
      - name: base_results
        type: object
      - name: report
        type: string

anti_patterns:
  - Reading network.json with sed / head / cat — these files run into the hundreds of thousands of lines; use json.load.
  - Indexing a bus by `bus_number - 1` instead of a `bus_num_to_idx` map — PGLib cases have non-contiguous bus IDs.
  - Treating a negative LMP as a bug — negative LMPs are physically valid in congested systems with trapped cheap generation.
  - Using OSQP for the DC-OPF-with-reserves solve — it is prone to failing on ill-conditioned problems; use CLARABEL.
  - Re-rounding dispatch, LMPs, or costs in the client_task — the scripts already round for display; re-rounding corrupts precision.
  - Scaling the reserve-requirement dual by baseMVA — the reserve constraint is written in MW, so its dual is already $/MWh.
  - Multiplying the nodal-balance dual by baseMVA to get LMPs — the balance constraint is in per-unit so the dual is $/hr-per-pu; divide by baseMVA (not multiply) to land in $/MWh.
  - Skipping the slack-bus angle fix (`θ[slack] = 0`) — without it, the DC-OPF is under-determined and the solver either errors or returns a meaningless angle vector.
```
