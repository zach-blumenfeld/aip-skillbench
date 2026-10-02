---
name: energy-market-counterfactual
description: "Clear a wholesale electricity market with DC-OPF plus reserve co-optimization and run a transmission-line counterfactual on a MATPOWER-format snapshot. Use when computing locational marginal prices (LMPs) and the reserve market clearing price (MCP) via CVXPY duals, identifying binding lines at >=99% loading, comparing a base case against a scenario that scales one line's thermal capacity, and producing a report.json with base_case / counterfactual / impact_analysis (cost_reduction, top-3 LMP drops, congestion_relieved). Covers MATPOWER bus / gen / gencost / branch column layouts, non-contiguous bus numbering, reserve capacity coupling P + R <= PMAX, slack-bus handling, and negative-LMP interpretation."
metadata:
  aip-version: "0.4a0"
  author: aip-skillbench
  version: "1.0"
---

# AIP runtime — format 0.4a0

You are executing an (Agent Instruction Protocol) AIP procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks using a graph-based workflow. AIP is portable, so while designed for execution with an AIP client and server, you, the agent can play both roles instead. 

## Running

If the `aip` command is available (`aip --help` succeeds), use it: run `aip run <this skill's folder> --input <start.json>` with the start step's inputs as JSON. When the run needs you it prints a JSON pause and exits with code 3. `paused` says why: `decision` — answer the listed questions; `review` — confirm or override the flagged answers; `client_task` — do the task and produce the keys in `expects`. Put your answer in a JSON file and run the `resume` command the pause printed. Repeat until the output has `"done": true`; `state` is the result. If `aip` is not available, execute the procedure yourself, following the semantics below.

Critical terminology:

- **Client**: whoever drives the run: posts each step's input, reviews uncertain decisions, performs client tasks, and makes the final call at every step. As a plain Agent Skill, it is the agent that activated the skill.
- **Server**: runs each step and validates its input against the step's `inputs`. Without one, the activating agent does this itself: runs scripts, answers decision questions by its own judgment, and follows routers.
- **State**: the JSON object a step receives. Each step declares its required keys as `inputs`; extra keys pass through.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to the client, `router` branches on a value in the state, `end` declares the final state's shape.

## Execution

The state is one JSON object. It starts as the start step's `inputs` and flows along `inputs_to`; each step's output is merged over it, so keys accumulate and extra keys pass through untouched. A step runs only if the state holds every key it declares in `inputs`, with the declared types. The client may change the state before any step runs; it has the final say at every step.

- **`execution`**: run `script` with one JSON object on stdin, `{"currentState": <state>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout; it is merged over the state.
- **`decision`**: answer each question against the state. Each answer collapses to one value under its question name and is merged over the state: a noul to `true`/`false`, a choice to its label, a score to its level number. With a decision model, an answer under its threshold is sent to the client to confirm or override before continuing; without one, the client answers the questions.
- **`client_task`**: render `template` with `{key}` from the state, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. The client performs the task, loading `references` if their descriptions apply, and returns the next step's `inputs`; they are merged over the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. That state is the procedure's result.

```yaml
purpose: >
  Clear a wholesale electricity market twice on a MATPOWER-format power-system snapshot
  and report the impact of a single transmission-line thermal-limit change. Both scenarios
  use DC-OPF with reserve co-optimization (CLARABEL solver): minimize polynomial generation
  cost subject to nodal DC power balance, generator PMIN/PMAX, per-generator reserve caps,
  capacity coupling P + R <= PMAX, a system reserve requirement, slack-bus angle = 0, and
  per-line thermal limits. LMPs come from the balance-constraint duals scaled by baseMVA;
  the reserve MCP comes from the reserve-requirement dual; binding lines are those at
  >=99% loading. The final report.json carries base_case, counterfactual, and impact_analysis
  (cost_reduction, top-3 buses by LMP drop, congestion_relieved flag).

trigger_when:
  - The user has a MATPOWER-format network snapshot (typically network.json) and asks to run
    market clearing or DC-OPF, produce LMPs / reserve MCP, or identify congested lines.
  - A "what if we relax this line's thermal capacity by X%" analysis is requested for a
    specific from/to bus pair.
  - The user asks to produce the base_case / counterfactual / impact_analysis report.json
    structure described in the task instruction.

do_not_use_when:
  - The snapshot is not in MATPOWER dict form (missing `bus`, `gen`, `branch`, `gencost`,
    `reserve_capacity`, `reserve_requirement`). Convert or use a different loader first.
  - The market model requires AC power flow, unit commitment (binary on/off), or multi-period
    optimization. This skill is single-period DC-OPF with continuous dispatch.
  - The counterfactual is anything other than scaling one line's thermal (RATE_A) limit
    (e.g. outages, topology changes, load shifts, generator additions).

steps:
  - name: solve-base
    kind: execution
    description: Solve base-case DC-OPF with reserve co-optimization on the unmodified network.
    inputs:
      - name: network_path
        type: string
        description: Absolute path to the MATPOWER-format network.json snapshot.
      - name: output_path
        type: string
        description: Absolute path where the final report.json will be written.
      - name: scenario_from_bus
        type: integer
        description: Bus number at one end of the transmission line to relax.
      - name: scenario_to_bus
        type: integer
        description: Bus number at the other end of the transmission line to relax.
      - name: scenario_delta_pct
        type: float
        description: Percent (not fraction) increase applied to the target line's RATE_A thermal limit. Pass 20.0 for +20%, not 0.20. Negative values tighten the limit.
    script: scripts/solve_base.py
    timeout: 900
    inputs_to: solve-counterfactual

  - name: solve-counterfactual
    kind: execution
    description: Scale the target line's thermal limit by (1 + delta_pct/100) and re-solve DC-OPF.
    inputs:
      - name: network_path
        type: string
      - name: scenario_from_bus
        type: integer
      - name: scenario_to_bus
        type: integer
      - name: scenario_delta_pct
        type: float
      - name: base_case
        type: object
        description: Base-case result from the previous step; passed through unchanged.
    script: scripts/solve_counterfactual.py
    timeout: 900
    inputs_to: compute-impact

  - name: compute-impact
    kind: execution
    description: Compute cost reduction, top-3 LMP drops, and congestion_relieved; write report.json.
    inputs:
      - name: output_path
        type: string
      - name: scenario_from_bus
        type: integer
      - name: scenario_to_bus
        type: integer
      - name: base_case
        type: object
      - name: counterfactual
        type: object
    script: scripts/compute_impact.py
    inputs_to: end

  - name: end
    kind: end
    description: Final state carrying the on-disk report path plus base_case, counterfactual, and impact_analysis.
    inputs:
      - name: report_path
        type: string
        description: Absolute path to the written report.json.
      - name: base_case
        type: object
      - name: counterfactual
        type: object
      - name: impact_analysis
        type: object

anti_patterns:
  - Reading a large MATPOWER network.json with sed / head / awk. Always use json.load — the file
    can be multi-MB with thousands of buses.
  - "Treating MATPOWER bus numbers as 0-indexed array positions. Bus IDs may be non-contiguous
    (e.g. 64 and 1501 in this task); build bus_num_to_idx = {int(buses[i,0]): i} and use it for
    every generator, branch, and constraint lookup."
  - Enforcing power balance as one aggregate "sum(Pg) == sum(Pd)" constraint. That drops the
    network, so LMPs collapse to a single system marginal cost. Use per-bus constraints
    Pg_at_bus - Pd == B[i, :] @ theta so each dual is that bus's LMP.
  - Solving without storing references to the balance and reserve constraints, then trying to
    read duals. CVXPY duals are only accessible on the constraint objects you kept a handle to.
  - Forgetting to scale LMPs by baseMVA. The balance constraint is in per-unit, so the raw dual
    is $/MWh_pu; multiply by baseMVA to report $/MWh.
  - Treating a negative LMP as a bug. Negative LMPs are physically valid in congested networks —
    adding load at that bus can relieve congestion and lower total cost.
  - "Reserve modeling shortcuts: omitting Rg >= 0, omitting the per-gen reserve_capacity cap, or
    omitting capacity coupling P + R <= PMAX. All three are required for reserve feasibility."
  - Using OSQP for the QP. It is unreliable on ill-conditioned DC-OPF-with-reserves; use CLARABEL.
  - Matching the counterfactual line in only one direction. The line may be stored as
    (from,to) or (to,from); check both orientations.
  - Sorting LMP deltas by absolute value when looking for the largest drop. Drops are the most
    negative deltas (cf_lmp - base_lmp), so sort ascending and take the first three.
  - Marking congestion_relieved = true whenever any line becomes unbound. The flag is specifically
    "was the target line binding in base AND is it no longer binding in the counterfactual".
```
