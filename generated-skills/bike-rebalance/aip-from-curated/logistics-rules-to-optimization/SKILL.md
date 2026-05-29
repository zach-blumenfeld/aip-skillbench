---
name: logistics-rules-to-optimization
description: Translate logistics and operations rules into optimization variables and constraints. Use when an operations problem describes vehicles, routes, depots, pickups, dropoffs, inventory, capacity, assignments, time windows, service targets, penalties, resource limits, or other business rules that need to become an optimization model.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Translate logistics and operations rules stated in natural language into
  optimization variables, constraints, and an objective expressed as
  PySCIPOpt. The same translation pattern covers transportation, dispatch,
  rebalancing, warehouse moves, staffing, scheduling, assignment, capacity
  planning, production, and service-level problems — not only routing.

trigger_when:
  - Problem statement gives operational rules in words and the agent must turn them into an optimization model.
  - User mentions vehicles, routes, depots, pickups, dropoffs, inventory, capacity, assignments, time windows, service targets, penalties, or resource limits.
  - Task asks for a rebalancing, dispatch, scheduling, or assignment plan and the answer must come from a solver.

do_not_use_when:
  - The problem already supplies a fully built optimization model and only asks for solver invocation or output formatting.
  - The task is descriptive analysis with no decisions to optimize.

steps:
  - name: list-entities
    description: >
      Enumerate the entities the problem describes — vehicles, locations,
      depots, jobs, workers, machines, products, arcs, time periods. Record
      their identifiers and per-entity attributes (capacity, demand, time
      window, distance/travel time, initial inventory, fixed cost) directly
      from the problem statement.
    outputs:
      - name: entities
        type: object
        description: Map of entity kind to identifier lists plus per-entity attribute tables.

  - name: choose-variables
    description: >
      Pick the decision variable type per decision. Use binary variables for
      yes/no choices (selection, arc-used, facility-open), integer variables
      for counts, loads, inventory, units moved, and continuous variables for
      time, flow, cost, utilization, or fractional quantities. Use integer
      variables for physical unit counts when the output must be
      integer-valued. Instantiate the right variable shape using the
      templates in `references/variable-patterns.md` — selection/assignment,
      route arcs, visit indicator, or quantity/load/inventory/time. Define
      visit from route arcs rather than creating a second binary unless the
      model needs it repeatedly.
    inputs:
      - name: entities
        type: object
    outputs:
      - name: variable-set
        type: list[object]
        description: Per-variable declarations — name, vtype (B/I/C), lower/upper bounds, index domain.

  - name: translate-rules
    description: >
      Walk every business rule in the problem and convert it into one of
      these canonical patterns — conservation (what enters equals what
      leaves, plus or minus changes), capacity (quantity cannot exceed a
      limit), linking (a quantity is allowed only if a binary decision is
      active), assignment (exactly one, at most one, or at least one
      choice), sequence (if one action follows another, update
      load/time/state), compatibility (prohibit impossible combinations),
      and soft penalty (add slack for unmet demand or violation cost).
      Match each rule against the lookup table in
      `references/rule-pattern-table.md`, then emit the PySCIPOpt
      constraint by adapting the snippets in
      `references/constraint-examples.md`. For inventory pickup/dropoff or
      rebalancing problems, additionally apply
      `references/inventory-pickup-dropoff.md` to introduce signed service
      variables and station-stock / free-space caps.
    inputs:
      - name: variable-set
        type: list[object]
    outputs:
      - name: constraints
        type: list[object]
        description: Per-constraint records — the business rule it implements, the indices it ranges over, and the generated PySCIPOpt code.

  - name: assemble-objective
    description: >
      Build the objective last from named components — travel cost, fixed
      cost, labor cost, inventory penalty, unmet demand penalty — following
      `references/objective-assembly.md`. Keep components named in the code
      so each contribution stays interpretable and can be recomputed
      independently during validation.
    inputs:
      - name: variable-set
        type: list[object]
      - name: constraints
        type: list[object]
    outputs:
      - name: objective
        type: object
        description: Sense (minimize/maximize) plus named cost components and the assembled `setObjective` expression.

  - name: validate-solution
    description: >
      After solving, independently recompute routes, loads, assignments,
      inventory, penalties, and the objective from the solved variable
      values. Do not return the solver's reported objective without
      recomputing it — independent recomputation is what catches sign
      errors, off-by-one indexing, big-M leakage, and constraint typos.
      For pickup/dropoff models, extract `picked_up = max(service_value, 0)`
      and `dropped_off = max(-service_value, 0)` from the signed service
      variable.
    inputs:
      - name: objective
        type: object
    outputs:
      - name: validated-output
        type: object
        description: Recomputed routes, loads, assignments, inventory, penalties, and objective components; any mismatch against the solver's reported values flagged.

scenarios:
  - need: Rebalance a bike-share network — move bikes between stations toward a target inventory using a fleet of trucks.
    context: >
      Trucks start and end at a depot, have load capacity, stations have
      storage capacity, and each station has a target pickup or dropoff
      quantity that may be partially unmet at a penalty.
    action: >
      Treat trucks as vehicles and stations as locations. Use arc binaries
      `x[v, i, j]`, a signed integer `service[v, i]` per visit, integer
      truck load `load[v, i]`, and nonnegative slack `unmet[i]` against the
      station target. Apply depot start/end, route continuity, signed-load
      transition along arcs, station stock/free-space caps, and absolute
      deviation against the target. Objective minimizes travel cost plus
      unmet-target penalty.
    outcome: >
      Routes per truck, signed pickup/dropoff per stop, and per-station
      unmet quantity — all independently recomputed from the variable
      values before reporting.

  - need: Vehicle routing with time windows and optional vehicles.
    action: >
      Use arc binaries `x[v, i, j]`, optional `use_vehicle[v]` binaries to
      gate depot start/end, continuous `arrival[v, i]` variables, and
      travel-time propagation along selected arcs guarded by big-M from the
      horizon. Apply time-window bounds on arrival only when the location
      is visited.

  - need: Soft demand with absolute deviation penalty.
    action: >
      Introduce nonnegative `dev[i]` and constrain
      `actual[i] - target[i] <= dev[i]` and `target[i] - actual[i] <= dev[i]`.
      Never apply Python `abs()` to a solver expression.

anti_patterns:
  - Using Python `abs()` on solver expressions — model absolute deviation with two nonnegative-slack constraints instead.
  - Choosing a loose big-M when tight bounds are known — pick `M` from real variable bounds (e.g., `2 * vehicle_capacity`, `horizon`) to keep the LP relaxation strong.
  - Adding the global single-visit rule when a large pickup/dropoff target may need multiple vehicles serving one location — only use it when split service is genuinely forbidden.
  - Creating a standalone `visit[v, i]` binary when `quicksum(x[v, i, j] for j in to_nodes if j != i)` already expresses the same thing.
  - Writing the objective before the constraints — entities, variables, and constraints come first; the objective is step 4.
  - Returning the solver's reported objective as truth without independently recomputing it from the variable values.
  - Confusing per-vehicle at-most-once (`outgoing[v,i] <= 1`) with global single-visit — the per-vehicle form still permits a different vehicle to visit the same location.
```
