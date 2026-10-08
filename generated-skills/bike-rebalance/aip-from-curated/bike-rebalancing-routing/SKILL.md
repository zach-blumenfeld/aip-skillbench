---
name: bike-rebalancing-routing
description: Solve multi-vehicle bike-share (or any pickup/dropoff inventory) rebalancing as a SCIP routing MIP — depot start/end, vehicle capacity, signed station targets with penalised deviation, station stock/dock limits, great-circle distances from lat/lon, original station IDs in the report — then write and independently validate the routes, per-stop pickups/dropoffs, distance, penalty, and objective. Use for vehicle routing with pickups and dropoffs, bike or scooter rebalancing, PySCIPOpt/SCIP routing models, subtour elimination, or validating a rebalancing report against data.json.
compatibility: Python 3 with pyscipopt (PySCIPOpt 6.x, as in the task container); scripts are otherwise stdlib-only.
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
  Turn a rebalancing data file (depot, stations with lat/lon, initial bikes, dock capacity, signed
  net rebalancing target, vehicle count/capacity, penalty weight, distance metric) plus the task's
  wording into an optimised, validated route plan. A decision pins down the rules the wording
  implies; a PySCIPOpt script builds the routing MIP (arc binaries, arc-flow truck load, lifted-MTZ
  or connectivity-flow subtour elimination, linearised deviation penalty) and writes a canonical
  solution with original station IDs; the agent maps it to the task's output schema; a second
  script recomputes everything from the raw data and gates the result.

trigger_when:
  - A task gives depots, stations or customers with coordinates and asks for vehicle routes that pick up and drop off units (bikes, scooters, stock) to hit per-station targets.
  - The objective mixes travel distance with a penalty for missing targets, under vehicle and station capacity limits.
  - A routing or rebalancing MIP must be modelled and solved with SCIP / PySCIPOpt.
  - A routing report (routes, loads, distance, penalty) must be checked against its input data.

do_not_use_when:
  - Pure single-vehicle TSP or assignment with no load or inventory (the model still works but is overkill).
  - Time-windowed or multi-period scheduling as the core of the task — adapt-model can add rules, but start from references/rules-to-constraints.md instead.
  - The task forbids an exact solver and asks for a specific heuristic.

steps:
  - name: read-task
    kind: decision
    description: Settle the routing rules the task wording implies before any modelling.
    inputs:
      - name: task_text
        type: string
        description: The task's instructions verbatim, including the output specification.
      - name: data_path
        type: string
        description: Absolute path of the instance JSON (e.g. /root/data.json). Read it first; the scripts tolerate common key aliases and fail with the key list otherwise.
      - name: output_path
        type: string
        description: Absolute path the task wants the report written to.
      - name: solution_path
        type: string
        description: Absolute path for the canonical solution JSON (a working file next to output_path, e.g. /tmp/rebalancing_solution.json; may equal output_path when the task gives no schema).
      - name: initial_vehicle_load
        type: integer
        description: Bikes on each truck when it leaves the depot. 0 unless the task says otherwise.
      - name: earth_radius
        type: float
        description: Earth radius for great-circle distance, in the metric's unit. 0 = use the data's value if present, else 3960 (miles) / 6371 (km). Use the task's radius if it states one.
      - name: time_limit_seconds
        type: float
        description: SCIP time limit. Default 600; lower it if the task's runtime budget is tight (the best incumbent is still reported).
    questions:
      vehicles_must_be_used:
        type: noul
        instructions: Must every vehicle leave the depot and serve at least one station? Yes unless the task says vehicles are optional, may stay at the depot, or the count is a maximum ("up to K vehicles").
        criteria:
          true: Fixed fleet that all go out, or the task is silent (default).
          false: Explicitly optional vehicles / "at most K" / unused trucks allowed.
      split_service_allowed:
        type: noul
        instructions: May more than one vehicle visit and serve the same station? Yes unless the task says each station is served by exactly one vehicle or visited at most once overall. A target larger than one truck's capacity is strong evidence splitting must be allowed.
        criteria:
          true: Silent, or allows multiple visits across vehicles (each vehicle still visits a station at most once).
          false: Explicit "each station visited once" / "served by a single vehicle".
      end_empty_required:
        type: noul
        instructions: Must each truck return to the depot empty (or unload everything by the end)? No unless the task states it.
      penalty_form:
        type: choice
        instructions: How does the objective penalise missing a station's net rebalancing target? The objective is travel distance plus this penalty times penalty_weight.
        criteria:
          absolute_deviation: Per unit of |achieved net change − target|, over- and under-shoot alike; the default when the task says "deviation from target", "imbalance", or is silent.
          shortfall_only: Only unmet target units are penalised; exceeding a target is free.
          other: Squared deviation, per-station weights, fixed vehicle costs, route-length caps, time windows, or any rule beyond these two.
    thresholds:
      vehicles_must_be_used: 0.2
      split_service_allowed: 0.2
      end_empty_required: 0.2
      penalty_form: 0.7
    inputs_to: by-penalty-form

  - name: by-penalty-form
    kind: router
    description: The bundled solver covers absolute-deviation and shortfall penalties; anything else needs an adapted model.
    branch_on: penalty_form
    branches:
      absolute_deviation: solve
      shortfall_only: solve
      other: adapt-model

  - name: solve
    kind: execution
    description: Build and solve the rebalancing routing MIP in SCIP, reconstruct routes with original IDs, write the canonical solution.
    inputs:
      - name: data_path
        type: string
      - name: solution_path
        type: string
      - name: vehicles_must_be_used
        type: boolean
      - name: split_service_allowed
        type: boolean
      - name: end_empty_required
        type: boolean
      - name: penalty_form
        type: string
      - name: initial_vehicle_load
        type: integer
      - name: earth_radius
        type: float
      - name: time_limit_seconds
        type: float
    script: scripts/solve_rebalancing.py
    timeout: 3700
    inputs_to: write-deliverable

  - name: adapt-model
    kind: client_task
    description: Extend a copy of the solver for a rule outside the two supported penalty forms and run it.
    inputs:
      - name: task_text
        type: string
      - name: data_path
        type: string
      - name: solution_path
        type: string
    template: assets/adapt-model.md
    references:
      - path: references/rules-to-constraints.md
        description: Rule-to-constraint patterns (assignment, capacity, linking, time windows, travel-time propagation, precedence, route-duration caps, fixed costs, soft penalties, absolute deviation) and the PySCIPOpt template, reproducibility settings, and extraction checks. Load when writing the new constraint.
      - path: references/subtour-elimination.md
        description: MTZ, connectivity flow, static and iterative DFJ cuts with pros/cons and code. Load if the adapted model changes the arc set or shows subtours.
    inputs_to: write-deliverable

  - name: write-deliverable
    kind: client_task
    description: Map the canonical solution to the task's required output file, programmatically.
    inputs:
      - name: task_text
        type: string
      - name: output_path
        type: string
      - name: solution_path
        type: string
      - name: objective
        type: float
      - name: solver_status
        type: string
    template: assets/write-deliverable.md
    assets:
      - assets/canonical-solution-format.md
    inputs_to: validate

  - name: validate
    kind: execution
    description: Recompute routes, loads, station inventory, distance, deviation, penalty, and objective from the raw data and the written report.
    inputs:
      - name: data_path
        type: string
      - name: output_path
        type: string
      - name: solution_path
        type: string
    script: scripts/validate_report.py
    inputs_to: by-verdict

  - name: by-verdict
    kind: router
    description: Pass ends the run; failures are fixed and re-validated; an unrecognised report layout is checked by hand.
    branch_on: verdict
    branches:
      pass: end
      fail: fix-deliverable
      unparsed: manual-check

  - name: fix-deliverable
    kind: client_task
    description: Repair the report (or the model assumptions) the validator rejected, then re-validate.
    inputs:
      - name: output_path
        type: string
      - name: solution_path
        type: string
      - name: issues
        type: list[*]
      - name: recomputed
        type: object
    template: assets/fix-deliverable.md
    references:
      - path: references/geospatial-data.md
        description: ID/index mapping, coordinate checks, great-circle formula, route reconstruction and route data checks. Load if an issue concerns IDs, depot labels, or distances.
      - path: references/subtour-elimination.md
        description: Subtour methods and route-extraction checks. Load if an issue reports a disconnected cycle or repeated station.
    inputs_to: validate

  - name: manual-check
    kind: client_task
    description: Verify by hand a report whose layout the validator could not parse.
    inputs:
      - name: output_path
        type: string
      - name: solution_path
        type: string
    template: assets/manual-check.md
    references:
      - path: references/geospatial-data.md
        description: Route data checks and the tolerance-based distance comparison. Load for the hand check.
    inputs_to: end

  - name: end
    kind: end
    description: The validated report on disk, its objective, and the solver status.
    inputs:
      - name: output_path
        type: string
      - name: objective
        type: float
      - name: solver_status
        type: string
      - name: verdict
        type: string

anti_patterns:
  - Using station IDs as array indices or assuming they are 0..n-1 — map IDs to indices for the model and back for every report.
  - Euclidean distance on degrees, a different Earth radius than the task/data states, mixing miles and km, or rounding distances inside the objective.
  - Relying on degree/continuity constraints (or the truck-load variable) to prevent subtours — pickup/dropoff load can rise and fall, so it proves nothing about connectivity.
  - Adding a global single-visit rule when the task does not require it — a target larger than one truck's capacity then becomes unreachable.
  - Ignoring the data's sign convention — positive targets mean pick up only if the data says so; the script reads net_rebalancing_target_sign_convention.
  - Letting net pickup exceed the station's initial bikes or net dropoff exceed its free docks; a target that the stock cannot satisfy is a forced deviation, not an infeasibility.
  - Python abs()/max() on solver expressions instead of two linear slack inequalities.
  - Reporting objective, distance, or routes copied from solver internals without recomputing them from coordinates and the written file.
  - Retyping routes or numbers into the output by hand instead of transforming the canonical solution in code.
  - Claiming optimality when SCIP stopped at its time limit — report the incumbent and the gap.
  - Installing another optimisation package when PySCIPOpt is available in the container.
```
