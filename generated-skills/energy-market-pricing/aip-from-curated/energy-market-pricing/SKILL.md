---
name: energy-market-pricing
description: "Clear a DC electricity market on a MATPOWER-format power system network — jointly dispatch generation and operating reserves, extract locational marginal prices (LMPs) and the reserve clearing price from the optimization duals, identify binding transmission constraints, and report total cost, load, generation, and reserves. Use when asked to compute LMPs, nodal prices, DC-OPF with reserve co-optimization, congestion analysis, or an energy market clearing result from a `network.json` MATPOWER file."
compatibility: Reproduces the task's container (python3 + pip) if numpy/cvxpy/clarabel are missing. For local `aip run` with the CLI's own Python, pre-install deps into `./scratch/venv` and prefix the command with the venv's PYTHONPATH.
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
  Clear a DC electricity market on a MATPOWER-format power system network:
  jointly dispatch generation and operating reserves to minimize total cost
  subject to generator limits, reserve-capacity coupling, nodal power balance
  (DC approximation), and line thermal limits; then extract locational
  marginal prices and the reserve clearing price from the optimization duals,
  identify binding transmission constraints, and report system totals.

trigger_when:
  - Compute LMPs or nodal electricity prices for a given power system network.
  - Run DC optimal power flow with operating-reserve co-optimization.
  - Identify binding transmission constraints and congestion rents.
  - Produce an energy market clearing (dispatch, prices, reserves) from a MATPOWER-format `network.json`.
  - Set up a baseline for counterfactual analysis of transmission constraints.

do_not_use_when:
  - Full AC power flow is required — voltage magnitudes, reactive power, or losses must be modeled.
  - Unit commitment is required — generator on/off binary decisions, startup/shutdown costs over time.
  - Multi-period / stochastic dispatch across time intervals is required.
  - The network file is not MATPOWER-shaped (no `bus`/`gen`/`branch`/`gencost` arrays).

steps:
  - name: clear-market
    kind: execution
    description: >
      Load the MATPOWER-format network at `network_path`, build the DC susceptance
      matrix from branch reactances using a bus-number→index mapping, formulate a
      CVXPY DC-OPF problem with reserve co-optimization (per-generator Pmin/Pmax,
      reserve non-negativity, reserve capacity, Pg+Rg≤Pmax coupling, system
      reserve requirement, slack-bus angle = 0, nodal balance per bus, line
      thermal limits), solve with CLARABEL, then extract per-generator dispatch
      and reserves (MW), per-bus LMPs ($/MWh, scaled by baseMVA from the
      balance-constraint duals), the reserve clearing price ($/MWh from the
      reserve constraint dual), lines at ≥99% loading, and system totals (cost,
      load, generation, reserves). Script bootstraps numpy, cvxpy, and clarabel
      if the container lacks them. Consult `references/matpower-format.md` for
      the bus/gen/branch/gencost column layouts and `references/dc-opf-formulation.md`
      for the full LP/QP formulation, dual→LMP scaling, binding-line definition,
      solver choice, and the counterfactual-analysis sketch.
    inputs:
      - name: network_path
        type: string
        description: >
          Absolute path to a MATPOWER-format JSON file with `baseMVA`, `bus`,
          `gen`, `branch`, `gencost`, `reserve_capacity`, and `reserve_requirement`.
          In the task container this is typically `/root/network.json`.
    script: scripts/solve_dcopf.py
    inputs_to: end

  - name: end
    kind: end
    description: >
      Energy market clearing result. `generator_dispatch` lists each
      generator's energy output and reserve award in MW; `lmp_by_bus` gives
      the locational marginal price at every bus in $/MWh (negative values
      are valid under congestion); `binding_lines` lists transmission lines
      at ≥99% of thermal limit; `totals` carries cost ($/hr), load,
      generation, and reserves (all MW); `reserve_mcp_dollars_per_MWh` is
      the system-wide reserve clearing price.
    inputs:
      - name: generator_dispatch
        type: list[*]
        description: Per-generator records {id, bus, output_MW, reserve_MW, pmax_MW}.
      - name: lmp_by_bus
        type: list[*]
        description: Per-bus records {bus, lmp_dollars_per_MWh}.
      - name: binding_lines
        type: list[*]
        description: Lines with |flow|/RATE_A ≥ 99%; records {from, to, flow_MW, limit_MW}.
      - name: totals
        type: object
        description: System totals {cost_dollars_per_hour, load_MW, generation_MW, reserve_MW}.
      - name: reserve_mcp_dollars_per_MWh
        type: float
        description: Dual value of the system reserve requirement constraint.

anti_patterns:
  - Reading large network JSON files line-by-line with sed/head/tail instead of `json.load` — wastes time and context.
  - Indexing arrays by `bus_number - 1`. Bus numbers may be non-contiguous; always build and use a `bus_num_to_idx` mapping.
  - Mis-scaling the LMP. The balance constraint is in per-unit while the cost is a function of `Pg*baseMVA`; the correct conversion is `LMP = dual / baseMVA`. Multiplying instead inflates every LMP by a factor of 10,000 on a `baseMVA = 100` case.
  - Treating a negative LMP as an error. Negative LMPs are physically valid in congested networks where cheap generation is trapped behind a binding line.
  - Enforcing total-generation = total-load globally in place of per-bus nodal balance. Doing so collapses the LMP vector to a single system price and hides congestion.
  - Solving with OSQP. OSQP fails on ill-conditioned DC-OPF-with-reserves problems; use CLARABEL.
  - Omitting the capacity-coupling constraint `Pg*baseMVA + Rg ≤ Pmax`. Without it, a generator can simultaneously sell more energy than its nameplate and reserve capacity.
  - Hard-coding NCOST=3 (quadratic). The script branches on `gencost[i, 3]` so linear and constant-cost generators are handled correctly.
```
