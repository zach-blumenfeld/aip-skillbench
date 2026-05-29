---
name: logistics-rules-to-optimization
description: Translate logistics and operations rules into optimization variables and constraints. Use when an operations problem describes vehicles, routes, depots, pickups, dropoffs, inventory, capacity, assignments, time windows, service targets, penalties, resource limits, or other business rules that need to become an optimization model.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Translate logistics and operations business rules (vehicles, routes,
  depots, pickups, dropoffs, inventory, capacity, assignments, time
  windows, service targets, penalties, resource limits) into optimization
  variables and constraints. The same translation pattern applies to
  routing, transportation, dispatch, rebalancing, warehouse moves,
  staffing, scheduling, assignment, capacity planning, production, and
  service-level problems — not only routing.

trigger_when:
  - The problem statement describes operational entities such as vehicles, locations, depots, jobs, workers, machines, products, arcs, or time periods.
  - Business rules involve capacity, conservation, assignment, sequence, time windows, compatibility, or service-level targets that need to become an optimization model.
  - The model needs decision variables (binary, integer, or continuous) for routing, dispatch, rebalancing, scheduling, assignment, allocation, packing, production, or service-level decisions.
  - Soft penalties or unmet-demand slack must be added on top of an existing optimization model.
  - Pickup/dropoff or material-movement rules need to be encoded with net inventory effects.

do_not_use_when:
  - The problem reduces to a closed-form formula or a single-pass greedy with no decisions to optimize.
  - The agent already has a tested and validated model and only needs to solve / extract results.
  - The task is a pure heuristic (e.g., savings, sweep, OR-Tools routing) that does not expose decision variables.

scope_and_approval: >
  Read-only against the input data. Writes only the agent's own modeling
  artefacts and the requested report file. No external services. This
  skill describes *how* to model — it does not by itself solve. Pair with
  `scip-opt` (or another solver skill) to optimize the resulting model
  and with `routing-subtour-elimination` when the model uses binary arc
  variables.

steps:
  - name: list-entities
    description: >
      Enumerate the entities in the problem (vehicles, locations, depots,
      jobs, workers, machines, products, arcs, time periods). Establish
      explicit index sets and any ID-to-index mappings when input
      identifiers are not contiguous. The list of entities determines
      the *shape* of every variable family in the next step.
    inputs:
      - name: problem-data
        type: object
        description: Parsed problem input — capacities, targets, costs, coordinates, time horizons, etc.
    outputs:
      - name: entities
        type: object
        description: Named index sets (e.g., vehicles, locations, periods, arcs) plus ID-to-index maps where needed.

  - name: choose-decision-variables
    description: >
      For each decision in the problem, pick a variable type — binary for
      yes/no choices (selection, mode, arc used), integer for counts and
      physical units (load, inventory, units moved, slack on discrete
      targets), continuous for time, flow, cost, utilization, fractional
      quantities, and MTZ ordering. Set tight `lb`/`ub` from real bounds
      so the relaxation is tight and any linking constraint has a
      non-arbitrary big-M. Load `references/variable-snippets.md` for
      ready scaffolds (selection, route arcs, visit indicator, load,
      inventory, arrival, signed service).
    depends_on: [list-entities]
    inputs:
      - name: entities
        type: object
    outputs:
      - name: decision-variables
        type: object
        description: Map of variable family name to its solver variable dict.

  - name: translate-business-rules
    description: >
      Walk each business rule in the problem statement and convert it
      into one of seven patterns — **conservation** (what enters equals
      what leaves), **capacity** (quantity cannot exceed a limit),
      **linking** (a quantity is allowed only if a binary is active),
      **assignment** (exactly / at most / at least one), **sequence**
      (state along the route updates from one action to the next),
      **compatibility** (forbid impossible combinations), **soft
      penalty** (allow violation with explicit slack). Use
      `references/rule-patterns.md` for the rule → variable → constraint
      lookup table and `references/constraint-snippets.md` for runnable
      blocks (capacity, quantity-when-active, soft demand, absolute
      deviation, depot start/end, route continuity, global single-visit,
      load/state transition, time windows, inventory balance). When the
      problem is rebalancing or material movement (some nodes are
      pickups, some are dropoffs, the target is a net change), load
      `references/pickup-dropoff.md` and follow the signed-service
      convention.
    depends_on: [choose-decision-variables]
    inputs:
      - name: decision-variables
        type: object
    outputs:
      - name: constraint-model
        type: object
        description: Solver model with hard and soft constraints installed; mapping from each business rule to the constraint(s) that encode it.

  - name: assemble-objective
    description: >
      Build the objective as a sum of **named components** (e.g.,
      `travel_cost`, `fixed_cost`, `labor_cost`, `inventory_holding_cost`,
      `unmet_demand_penalty`). Keep each component as its own `quicksum`
      so it can be reported and independently revalidated. Load
      `references/objective-assembly.md` for component patterns, naming
      guidance, and penalty-weight calibration.
    depends_on: [translate-business-rules]
    inputs:
      - name: decision-variables
        type: object
      - name: constraint-model
        type: object
    outputs:
      - name: objective-components
        type: object
        description: Named expressions whose sum is the solver objective.

  - name: extract-and-validate
    description: >
      After solving, reconstruct routes, loads, assignments, inventory,
      and penalties from variable values (compare binaries against 0.5,
      round integers explicitly). Recompute every named objective
      component from the reconstructed solution and assert it matches
      the solver-reported value within tolerance (1e-6). Treat solver
      feasibility as necessary but not sufficient — the model may be
      *internally* consistent yet *externally* wrong (e.g., a mis-typed
      penalty coefficient, wrong distance metric, or missing rule).
      Fail loudly on mismatch rather than patching the report.
    depends_on: [assemble-objective]
    inputs:
      - name: decision-variables
        type: object
      - name: objective-components
        type: object
    outputs:
      - name: report
        type: object
        description: Final structured answer, validated against the reconstructed solution.

scenarios:
  - need: Bike-share rebalancing with per-station targets and a per-bike unmet penalty.
    context: >
      Each station has a net rebalancing target (positive = pickup,
      negative = dropoff). Vehicles share a depot and capacity. Travel
      distance plus penalty × total unmet is minimized.
    action: >
      Entities: vehicles, stations, arcs. Variables: binary route arcs
      `x[v, i, j]`, integer load along the route, signed integer
      `service[v, i]` (positive = pickup, negative = dropoff),
      nonnegative integer `unmet[i]`. Rules: depot start / end, route
      continuity, per-vehicle at-most-once, station inventory bounds
      via net change, absolute deviation between net change and target,
      load propagation along selected arcs (big-M = 2 × vehicle
      capacity). Objective: `travel_cost + penalty_weight * sum(unmet)`.
    outcome: >
      A multi-vehicle pickup/dropoff routing model whose objective is
      directly comparable against a SCIP benchmark.
  - need: Heterogeneous-fleet delivery with a fixed cost per used vehicle.
    action: >
      Add an optional `use_vehicle[v]` binary; gate depot start/end on
      it; add `fixed_cost[v] * use_vehicle[v]` to the objective.
    outcome: Vehicles with no economical route remain idle; the objective trades fixed vs travel cost cleanly.
  - need: Multi-period inventory replenishment with limited storage.
    action: >
      Variables: integer `inventory[i, t]` bounded by storage capacity,
      nonnegative `outbound[i, t, dst]` bounded by `inventory[i, t]`.
      Constraints: inventory balance across periods, capacity per
      period. Objective: holding cost + transport cost + unmet-demand
      penalty.
    outcome: Inventory levels stay within physical bounds and demand penalties surface periods of structural shortfall.

anti_patterns:
  - Calling Python's built-in `abs()` on a solver expression. Linearise with two `<=` inequalities and a nonnegative slack instead.
  - Adding the global single-visit rule when a single location's target can legitimately need more than one vehicle. Use per-vehicle `outgoing[v, i] <= 1` instead and only add the global rule when split service is genuinely forbidden.
  - Picking an arbitrary big-M for linking constraints when capacity, vehicle capacity × 2, max distance, or horizon would give a tight real bound.
  - Modeling routing with only degree + continuity constraints. Disconnected sub-cycles will appear — add MTZ, flow-based, or DFJ subtour elimination (`routing-subtour-elimination` skill).
  - Treating vehicle load as a connectivity flow in a pickup/dropoff model. Load can decrease as well as increase along the route and does not prove connectivity.
  - Reporting the solver objective without independently reconstructing routes, loads, inventory, and penalties from variable values. The model can be feasible yet wrong.
  - Forgetting to gate route-state propagation (load, arrival, battery, inventory) on the arc binary. Without the gate, disconnected stops update state and the solver finds spurious "optimal" solutions.
  - Allowing both pickup and dropoff at the same stop when the rule forbids it. Use a single signed `service[v, i]` (positive = pickup, negative = dropoff) rather than separate variables — this enforces mutual exclusion structurally.
  - Duplicating a `visit` binary when a `quicksum` over outgoing arcs would do. Only introduce a standalone visit variable when it appears in many constraints.
  - Squashing the objective into a single expression with no named components. Recomputing the objective independently after the solve becomes impossible.
  - Patching the report to make numbers reconcile rather than fixing the underlying model or extraction bug.
```
