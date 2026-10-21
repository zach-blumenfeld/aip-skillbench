---
name: bike-rebalancing-scip
description: Plan nightly bike-share rebalancing - vehicle routes from a depot plus per-stop pickup/drop-off quantities that meet each station's net_rebalancing_target - by solving a SCIP mixed-integer model (PySCIPOpt) over great-circle distances, then writing and independently verifying report.json. Use for bike/scooter rebalancing, pickup-and-delivery vehicle routing with vehicle capacity, station capacity, unmet-target penalties, depot routes, and data.json inputs with station latitude/longitude.
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
  Turn a bike-share rebalancing instance (data.json: vehicle_count, vehicle_capacity,
  penalty_weight, depot and station coordinates, net_rebalancing_target, initial_bikes,
  station_capacity) into report.json: one depot-to-depot route per vehicle with
  pickup/drop-off quantities and loads at every stop, station totals, and the objective
  (great-circle travel miles + penalty_weight x unmet bikes). A route local search seeds a
  SCIP MIP (arc-load flow, lifted MTZ, exact subtour-cut separation) that proves optimality
  in well under a minute on 15-station, 2-vehicle instances and keeps improving larger ones;
  an independent checker recomputes every number from data.json.

trigger_when:
  - A task asks for routes and pick-up/drop-off operations for bike, scooter, or similar rebalancing vehicles.
  - A data.json lists a depot, stations with latitude/longitude, net_rebalancing_target, initial_bikes, and station_capacity, plus vehicle_count and vehicle_capacity.
  - The objective is travel distance plus a per-unit penalty for unmet rebalancing targets.

do_not_use_when:
  - Stations have visit time windows, shift lengths, or ordered inventory over the night; the model only constrains end-of-night inventory (see references/model.md to extend it).
  - Distances must come from a road network or a metric other than great-circle miles.

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - pyscipopt

steps:
  - name: inspect-instance
    kind: execution
    description: >
      Parse data.json, reject malformed data (duplicate ids, coordinates out of range,
      initial_bikes outside 0..station_capacity, non-great-circle metric), and summarize
      the instance for the rule-reading decision.
    inputs:
      - name: task_statement
        type: string
        description: The task's full instructions, verbatim (the rules list and report format).
      - name: data_path
        type: string
        description: Absolute path to data.json in this environment, e.g. /root/data.json.
      - name: report_path
        type: string
        description: Where to write report.json; /root/report.json unless the task names another path.
      - name: earth_radius_miles
        type: float
        description: Earth radius the task statement declares for great-circle distance (3960.0 when it says "Earth radius 3960.0").
      - name: time_limit_seconds
        type: float
        description: Wall-clock limit for the first solve (route search plus SCIP). 120 proves optimality on ~15 stations and 2 vehicles; lower it only if the task's time budget is tighter. Capped at 540 (step timeout 600).
      - name: polish_time_limit_seconds
        type: float
        description: Time limit for the warm-started re-solve, used only when the first solve stops without proving optimality. 300 unless the task's time budget is tighter. Capped at 840 (step timeout 900).
    script: scripts/inspect_instance.py
    outputs:
      - name: instance_summary
        type: object
        description: Station and vehicle counts, capacity, penalty, sign convention, total pickup and drop-off targets, and stations whose target exceeds stock or free docks.
    inputs_to: read-rules

  - name: read-rules
    kind: decision
    description: >
      Read the task's routing rules and fix the three modelling switches the solver needs.
      Each answer must follow the statement's wording, not what seems operationally typical.
    inputs:
      - name: task_statement
        type: string
      - name: instance_summary
        type: object
    questions:
      loaded_departure_allowed:
        type: noul
        instructions: >
          May a vehicle leave the depot already carrying bikes (start_load > 0)?
        criteria:
          true: The statement only bounds start_load (e.g. ">= 0 and <= vehicle_capacity") or reports it as a decision, and nowhere says vehicles leave empty.
          false: The statement says vehicles start empty, start_load must be 0, or the depot holds no bikes.
      every_vehicle_must_visit:
        type: noul
        instructions: >
          Must every vehicle visit at least one station (no vehicle may stay at the depot)?
        criteria:
          true: The statement says a vehicle must visit some stations / cannot just stay at the depot, or that all vehicles are used.
          false: Vehicles are optional and an idle vehicle may report route ["depot_start", "depot_end"].
      exclusive_station_visits:
        type: noul
        instructions: >
          Does the statement forbid two different vehicles from visiting the same station?
          "A vehicle can visit a station no more than once" is a per-vehicle rule and is false here.
        criteria:
          true: Each station may be served by at most one vehicle in total.
          false: Only per-vehicle repeat visits are forbidden, or nothing is said; split service across vehicles is allowed.
    thresholds:
      loaded_departure_allowed: 0.3
      every_vehicle_must_visit: 0.2
      exclusive_station_visits: 0.2
    inputs_to: solve

  - name: solve
    kind: execution
    description: >
      Run a route local search (relocate, swap, 2-opt, add/remove and split visits; greedy
      per-route services, exact per route for each start load) for ~10% of the limit, fix
      its routes to get exact services, then hand that plan and an always-feasible trivial
      plan to the MIP (per-vehicle arc binaries, one signed integer service per stop so a stop
      never both picks up and drops off, arc-load flow bounded by vehicle_capacity, final
      station inventory in [0, station_capacity], absolute-deviation unmet slack, lifted MTZ,
      exact generalized subtour cuts, vehicle-symmetry cut). Solve with SCIP for the rest of
      the limit, rebuild every report number from the incumbent, and write report.json. solve_status is "optimal" when SCIP proved it, "incumbent" when the
      time limit stopped it with a feasible plan. Read references/model.md (the model's
      math, rule-to-constraint table, subtour-elimination options) only if this step fails
      or the statement has a rule the read-rules switches do not cover.
    inputs:
      - name: data_path
        type: string
      - name: report_path
        type: string
      - name: earth_radius_miles
        type: float
      - name: time_limit_seconds
        type: float
      - name: loaded_departure_allowed
        type: boolean
      - name: every_vehicle_must_visit
        type: boolean
      - name: exclusive_station_visits
        type: boolean
    script: scripts/solve.py
    timeout: 600
    outputs:
      - name: solve_status
        type: string
        description: '"optimal" or "incumbent".'
      - name: solve_objective
        type: float
        description: Objective of the written report (travel miles + penalty).
      - name: solve_gap
        type: float
        description: SCIP's relative optimality gap at stop (0 when optimal).
    inputs_to: by-solve-status

  - name: by-solve-status
    kind: router
    description: A proven optimum goes straight to verification; an unproven incumbent gets a longer warm-started solve first.
    branch_on: solve_status
    branches:
      optimal: verify
      incumbent: polish

  - name: polish
    kind: execution
    description: >
      Restart the route search from the written report's routes (new random seed), rebuild
      the same model, give SCIP both plans as starting solutions, and solve again within
      polish_time_limit_seconds. Overwrites report.json only if the new plan is
      at least as good, so the report never gets worse.
    inputs:
      - name: data_path
        type: string
      - name: report_path
        type: string
      - name: earth_radius_miles
        type: float
      - name: polish_time_limit_seconds
        type: float
      - name: loaded_departure_allowed
        type: boolean
      - name: every_vehicle_must_visit
        type: boolean
      - name: exclusive_station_visits
        type: boolean
    script: scripts/polish.py
    timeout: 900
    outputs:
      - name: polish_status
        type: string
        description: '"optimal" or "incumbent" after the re-solve.'
      - name: polish_objective
        type: float
        description: Objective of the report now on disk.
      - name: polish_gap
        type: float
        description: Relative gap at stop of the re-solve.
    inputs_to: verify

  - name: verify
    kind: execution
    description: >
      Independently check report.json against data.json and every task rule: all vehicles
      1..vehicle_count and all stations present; routes start depot_start, end depot_end,
      match the stops, visit some station, never repeat a station; start_load,
      load_after_stop, end_load within [0, vehicle_capacity] and load_after_stop =
      previous + picked - dropped; no stop both picks up and drops off; station totals equal
      the sum of stops; final inventory within [0, station_capacity]; unmet, penalty,
      great-circle distance, and objective recomputed. Fails listing every violation; do not
      hand-edit the report to pass, fix the cause and rerun from solve.
    inputs:
      - name: data_path
        type: string
      - name: report_path
        type: string
      - name: earth_radius_miles
        type: float
      - name: loaded_departure_allowed
        type: boolean
      - name: every_vehicle_must_visit
        type: boolean
      - name: exclusive_station_visits
        type: boolean
    script: scripts/verify.py
    outputs:
      - name: verified_objective
        type: float
        description: travel_distance_miles + unmet_rebalancing_penalty, recomputed.
      - name: verified_travel_distance_miles
        type: float
        description: Great-circle miles over all routes, recomputed from coordinates.
      - name: verified_unmet_rebalancing_penalty
        type: float
        description: penalty_weight x total unmet bikes.
      - name: verified_total_unmet_rebalancing_amount
        type: float
        description: Sum over stations of abs(net_rebalancing_target - net_bike_change).
    inputs_to: end

  - name: end
    kind: end
    description: report.json is written at report_path and verified; the summary numbers below match it.
    inputs:
      - name: report_path
        type: string
      - name: instance_summary
        type: object
      - name: verified_objective
        type: float
      - name: verified_travel_distance_miles
        type: float
      - name: verified_unmet_rebalancing_penalty
        type: float
      - name: verified_total_unmet_rebalancing_amount
        type: float

anti_patterns:
  - Solving with a greedy heuristic or hand-built routes instead of the SCIP model; a feasible-looking plan is usually far from optimal.
  - Using station ids as array indices, or reporting internal indices instead of the original ids; ids are not 0..n-1.
  - Computing distance with haversine, a different Earth radius, Euclidean degrees, or rounded values; use the statement's great-circle formula and radius exactly.
  - Forbidding two vehicles from serving the same station when the rule is only "a vehicle visits a station at most once"; large targets (e.g. -34 with capacity 25) need split service.
  - Relying on vehicle load to prevent subtours; load rises and falls with pickups and drops, so it proves nothing about route connectivity.
  - Using Python abs() on solver expressions; the unmet slack is linearized with two inequalities.
  - Copying distance or objective from the solver instead of recomputing them from the routes and coordinates.
  - Omitting idle stations from the stations list or idle vehicles from the vehicles list; every station in data.json and every vehicle 1..vehicle_count must appear.
  - Hand-editing report.json after verify; any change must be rerun through verify.
```
