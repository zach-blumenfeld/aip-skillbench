---
name: scip-opt
description: SCIP optimization with PySCIPOpt. Use when facing an optimization problem with an objective, hard constraints, soft penalties, integer decisions, routing, assignment, scheduling, allocation, packing, capacity, inventory, or service-level rules. Prefer modeling and solving the problem with PySCIPOpt when it is available.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3 and PySCIPOpt (the open-source SCIP solver's Python bindings). Do not substitute another solver before checking pyscipopt is unavailable.
---

```yaml
purpose: >
  Model and solve mixed-integer optimization problems with PySCIPOpt.
  Covers the full loop — confirm SCIP is available, identify sets and
  indices, declare binary / integer / continuous decision variables,
  add hard constraints (conservation, capacity, bounds, linking,
  continuity, exclusion), linearize soft constraints with explicit
  slack variables, set a single objective with named cost and penalty
  components, pin reproducibility, solve under time and gap limits,
  and independently validate the extracted solution. For routing,
  assignment, packing, inventory-movement, scheduling, and allocation
  problems with rules that every answer must satisfy plus rules that
  carry an explicit penalty when violated, a SCIP-backed model plus an
  independent validator is usually safer than a greedy construction.

trigger_when:
  - The task asks to minimize or maximize an objective subject to constraints.
  - The request mentions cost, distance, time, unmet demand, or penalty as something to drive down.
  - The decisions are yes/no choices, route arcs, assignments, selected items, or an ordering.
  - The quantities are integer or continuous loads, inventory moves, served units, or slacks.
  - There are hard rules every valid answer must satisfy AND soft rules that can be violated with an explicit penalty.
  - Problem shape matches routing, assignment, scheduling, allocation, packing, capacity planning, or inventory rebalancing.

do_not_use_when:
  - The problem is a pure simulation, regression, or classification with no objective-and-constraints structure.
  - A closed-form or sort-and-pick algorithm clearly suffices and adding a solver would be ceremony.
  - PySCIPOpt is not available in the environment AND installing additional solvers is out of scope — re-plan instead of swapping in a different solver silently.

scope_and_approval: >
  All operations are local — script imports, model construction in
  memory, in-process SCIP solve, and post-solve validation of the
  agent's own output. No network calls, no destructive filesystem
  writes beyond the artefacts the calling task requests. Safe to run
  without prompting; the validator at the end is itself a guardrail
  against silently shipping a wrong objective.

steps:
  - name: check-availability
    description: >
      Confirm PySCIPOpt is importable BEFORE committing to a SCIP-backed
      approach. The curated source is emphatic — do not start by
      installing another optimization package. If the import fails,
      stop and re-plan with the user rather than silently swapping in a
      different solver.
    script: scripts/check_pyscipopt.py
    outputs:
      - name: pyscipopt_available
        type: boolean
        description: True when pyscipopt is importable; otherwise the script raises RuntimeError.

  - name: identify-sets-and-indices
    description: >
      Name the index sets the model ranges over — vehicles K, stations
      N, jobs J, periods T, arcs A. When input IDs are not contiguous
      (e.g. station_id strings), build an explicit mapping from the raw
      identifier to a 0-based index used by the variable dictionaries.
      Document the sets next to the variable declarations so the model
      remains readable when the constraint blocks grow.
    inputs:
      - name: problem_data
        type: object
        description: Raw inputs (stations, vehicles, demands, capacities, distances).
    outputs:
      - name: index_sets
        type: object
        description: Named index sets and any raw->index mappings used in variable construction.

  - name: define-decision-variables
    description: >
      Declare one variable family per kind of decision the model makes.
      Binary `vtype="B"` for choices, visits, assignments, route arcs,
      mode selection. Integer `vtype="I"` with explicit `lb`/`ub` for
      counts, loads, inventory moves, unmet units. Continuous (default)
      with `lb=0` for flows, costs, times, slacks, resource levels. Use
      dictionary comprehensions keyed by the index sets from the prior
      step. Reference `references/minimal_template.md` for the canonical
      naming pattern when starting fresh.
    depends_on: [identify-sets-and-indices]
    inputs:
      - name: index_sets
        type: object
    outputs:
      - name: decision_vars
        type: object
        description: Dictionaries of SCIP Vars grouped by family (e.g. x, amount, dev, order).

  - name: add-hard-constraints
    description: >
      Encode the rules every valid answer must satisfy — conservation
      (flow in equals flow out), capacity (sum of weights at a node
      stays under its limit), bounds (lb / ub), linking (`q[i] <=
      upper[i] * use[i]` so a quantity is only allowed when its switch
      is on), continuity (route degree balance), inventory limits, and
      mutual exclusion (at most one alternative chosen). For
      problem-specific structural shapes — assignment, route arcs +
      MTZ subtour elimination, binary activation — load
      `references/patterns.md` and copy the matching block.
    depends_on: [define-decision-variables]
    inputs:
      - name: decision_vars
        type: object

  - name: add-soft-constraints
    description: >
      Convert "violations are allowed but costly" rules into explicit
      slack variables. The canonical shape is absolute-deviation: add
      `dev[i] >= 0`, then BOTH `actual[i] - target[i] <= dev[i]` AND
      `target[i] - actual[i] <= dev[i]`. The minimization pulls
      `dev[i]` down to `|actual[i] - target[i]|`. NEVER write Python's
      `abs()` on a SCIP expression — it does not linearize and the
      model will fail or silently misbehave. Pattern code in
      `references/patterns.md` § Absolute Deviation Penalty.
    depends_on: [define-decision-variables]
    inputs:
      - name: decision_vars
        type: object
    outputs:
      - name: slack_vars
        type: object
        description: Slack / deviation variables introduced for each soft rule, indexed for use in the objective.

  - name: set-objective
    description: >
      Compose ONE objective from named components — typically
      `cost = quicksum(...)` plus `penalty = weight * quicksum(dev[i]
      for i in I)`. Keeping the components as named Python expressions
      makes later reconstruction in `extract-and-validate`
      straightforward and lets you echo each component in debug
      output. Call `model.setObjective(cost + penalty, "minimize")`
      (or "maximize") once.
    depends_on: [add-hard-constraints, add-soft-constraints]
    inputs:
      - name: decision_vars
        type: object
      - name: slack_vars
        type: object
        nullable: true
    outputs:
      - name: objective_components
        type: object
        description: Named cost / penalty / etc. expressions kept so they can be reconstructed from variable values after the solve.

  - name: configure-reproducibility
    description: >
      When repeatability matters (benchmark tasks, deterministic
      comparison runs), pin SCIP's randomization and threading. Call
      `set_reproducible(model)` from
      `scripts/set_reproducibility.py` — it iterates the curated list
      of seed and permutation params via `set_if_available`, swallowing
      errors for params this SCIP build does not expose, and forces
      `parallel/maxnthreads=1`. Skip only when the task explicitly
      tolerates non-determinism.
    script: scripts/set_reproducibility.py
    depends_on: [check-availability]

  - name: solve
    description: >
      Apply time and gap limits, then call `model.optimize()`. The
      curated defaults are 300 s wall clock and 1 % MIP gap; tighten
      or loosen per task. Immediately after the solve, call
      `require_incumbent(model)` (in `scripts/solve_helpers.py`) so a
      no-incumbent SCIP exit raises with a clear status string before
      any variable read happens.
    script: scripts/solve_helpers.py
    depends_on: [set-objective, configure-reproducibility]
    inputs:
      - name: objective_components
        type: object
    outputs:
      - name: solve_status
        type: string
        description: Lowercase SCIP status — `optimal`, `gaplimit`, `timelimit`, etc.
      - name: objective_value
        type: float
        description: model.getObjVal() once an incumbent exists.

  - name: extract-and-validate
    description: >
      Reconstruct the answer from variable values and validate it
      OUTSIDE SCIP. Use `is_selected(model, var)` from
      `scripts/solve_helpers.py` for the 0.5 binary threshold; pull
      integer / continuous values via `model.getVal(var)`. Then
      independently recompute each named objective component from the
      extracted decisions and call
      `assert_objective_component("cost", reported, recomputed)` to
      confirm the two agree within tolerance. SCIP feasibility is
      NECESSARY but NOT SUFFICIENT — the final reported file still
      needs problem-specific checks for output schema, route
      reconstruction, capacity, inventory, penalty arithmetic, and any
      task-defined service levels.
    script: scripts/solve_helpers.py
    depends_on: [solve]
    inputs:
      - name: objective_components
        type: object
      - name: solve_status
        type: string
    outputs:
      - name: solution
        type: object
        description: Problem-shape answer (selected items, routes, loads, schedules) ready to serialize.
      - name: validation_report
        type: object
        description: Per-component reported vs recomputed values plus pass/fail flags for the task-specific rule checks.

modes:
  - name: fresh-model
    body: >
      Building a new model from scratch. Start by reading
      `references/minimal_template.md`, then walk the steps in order.
      Reach for `references/patterns.md` whenever the problem matches
      one of the structural shapes there (assignment, binary
      activation, absolute deviation, route arcs, MTZ subtour).
  - name: extend-existing-model
    body: >
      The model already exists and a new constraint family or objective
      term needs to be added. Skip `identify-sets-and-indices` and
      `define-decision-variables`. Add the new vars / constraints in
      the appropriate step (hard or soft), update the named objective
      components, and re-run `extract-and-validate` end-to-end — never
      patch in a new term without re-validating, since component-level
      drift is the most common shipping bug.
  - name: routing
    body: >
      The problem involves vehicles visiting locations. Always pair
      `references/patterns.md` § Route Arcs with § MTZ Subtour
      Elimination — degree and continuity constraints alone permit
      disconnected cycles. The validator at the end must reconstruct
      the route as an ordered list of locations per vehicle and
      confirm it visits each required node exactly the required number
      of times.

scenarios:
  - need: Bike-rebalance — move bikes between stations under vehicle capacity, penalizing stations left away from a target inventory.
    context: >
      Decisions per vehicle are which stations to visit, in what
      order, and how many bikes to pick up / drop off at each.
      Stations have a target inventory; deviations are soft.
    action: >
      Binary x[k,i,j] for vehicle k traversing arc (i,j); integer
      load[k,i] for bikes carried; integer pickup[k,i] / dropoff[k,i]
      at each visit; dev[i] for absolute deviation from target.
      Hard: degree + continuity + MTZ + capacity link load <=
      cap * (sum of incoming arcs). Soft: absolute deviation per
      station. Objective: travel cost + penalty_weight *
      sum(dev[i]).
    outcome: >
      A reconstructed route per vehicle, per-station pickup / dropoff
      counts, and a validator that confirms reported travel cost and
      penalty equal the recomputed values from the extracted
      decisions.
  - need: Assignment — pack jobs onto machines under machine capacity to minimize fixed-plus-variable cost.
    context: >
      Each job goes to exactly one machine; each machine has a
      weight capacity; opening a machine pays a fixed cost.
    action: >
      Binary assign[i,j] for job i on machine j; binary open[j] for
      machine j active. Hard: sum_j assign[i,j] == 1, sum_i weight[i]
      * assign[i,j] <= cap[j] * open[j]. Objective: fixed cost *
      open[j] + variable cost * assign[i,j].
    outcome: >
      Job -> machine map plus the set of opened machines, validated
      by independently recomputing fixed and variable cost
      components.
  - need: Inventory rebalancing across periods with stockout penalties.
    context: >
      Discrete time periods; carryover inventory; demand each period;
      unmet demand carries a penalty.
    action: >
      Continuous inventory[t]; integer move[t]; continuous unmet[t]
      >= 0 with unmet[t] >= demand[t] - served[t]. Hard: inventory
      balance inventory[t] == inventory[t-1] + move[t] - served[t].
      Objective: holding cost + move cost + unmet penalty.
    outcome: >
      Period-by-period plan plus unmet-demand series, validated by
      reconstructing each cost component and asserting agreement
      with the solver-reported objective.

integrations:
  - partner: problem-specific validator script
    body: >
      `extract-and-validate` lifts the generic helpers
      (`is_selected`, `assert_objective_component`) into the model
      workflow, but task-specific checks — output schema, route
      reconstruction, service-level rules — still belong in a
      task-owned validator the agent writes alongside its solution.
      Treat the SCIP-side checks here as the floor, not the ceiling.
  - partner: data-loading / preprocessing skills
    body: >
      `identify-sets-and-indices` consumes whatever structure the
      preceding data-loading produces (CSV, JSON, in-memory dict).
      Keep that boundary clean — the modeling step should not parse
      raw files, and the data-loading step should not know about
      SCIP variable types.

anti_patterns:
  - Installing a different optimization package (e.g. PuLP, OR-Tools, Gurobi) before confirming PySCIPOpt is unavailable. Run `scripts/check_pyscipopt.py` first.
  - Writing `abs(actual[i] - target[i])` against SCIP expressions. Python's `abs()` does not produce a linear constraint. Always linearize with two inequalities into a `dev[i] >= 0` slack.
  - Treating soft constraints as hard. If the rule says "violations are allowed but penalized", introduce a slack variable — never `==` or strict `<=` it down to zero.
  - Building a routing model with degree and continuity constraints only. Disconnected subtours satisfy both; pair with MTZ (or another subtour-elimination scheme) every time. See `references/patterns.md`.
  - Reading variable values without first checking `model.getNSols() > 0`. SCIP can time-out with no incumbent; pulling values from that state yields garbage. Use `require_incumbent(model)`.
  - Reading `model.getVal(binary_var)` with `== 1` or `int(...)`. Use the 0.5 threshold via `is_selected(model, var)` — SCIP returns floats even for binaries.
  - Treating SCIP feasibility as final validation. Always independently reconstruct each named objective component AND each hard rule from the extracted decisions, and assert agreement within tolerance.
  - Hardcoding seeds inline scattered through the model. Call `set_reproducible(model)` once after construction so the param list lives in one place and missing-param errors are tolerated uniformly.
  - Stacking multiple objectives into the solver. SCIP optimizes one objective. Combine components with explicit weights (`cost + penalty_weight * penalty`) in a single `setObjective` call, and keep the components named so you can audit them after the solve.
```
