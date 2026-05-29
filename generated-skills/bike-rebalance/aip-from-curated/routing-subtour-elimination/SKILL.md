---
name: routing-subtour-elimination
description: Subtour-elimination methods for TSP, VRP, pickup/dropoff routing, and routing MIPs with binary arc variables. Use when route-continuity constraints may permit disconnected cycles and the model needs MTZ constraints, flow-based connectivity constraints, DFJ subset cuts, or lazy/iterative subtour cuts.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Add subtour-elimination constraints to routing MIPs with binary arc
  variables (TSP, VRP, pickup/dropoff routing). Degree and continuity
  constraints alone allow a vehicle to have one depot-to-depot path plus a
  separate closed cycle among stations. This procedure enforces base route
  constraints, selects an appropriate subtour-elimination method (MTZ,
  single-commodity flow, static DFJ, or lazy/iterative DFJ cuts), applies
  the chosen method, and validates the resulting routes.

trigger_when:
  - Building a routing MIP with binary arc variables x[v,i,j] for vehicles, depots, and stations.
  - The current model has degree/flow continuity constraints but no subtour-elimination logic.
  - Solver returns "optimal" routes that include a closed cycle disconnected from the depot.
  - A TSP, VRP, CVRP, PDP, or bike/scooter rebalancing model needs route connectivity guarantees.
  - Picking between MTZ, flow-based, DFJ, or lazy-cut subtour elimination.

do_not_use_when:
  - The routing model has no binary arc variables (e.g., pure assignment or column-generation master with prebuilt routes).
  - Routes are constructed by a heuristic (savings, sweep, OR-Tools routing) that already guarantees connectivity.
  - The model has only a single mandatory cycle through all nodes with no depot split — standard TSP cut libraries apply directly.

steps:
  - name: add-base-route-constraints
    description: >
      Add per-vehicle degree and flow-balance constraints over the
      depot_start/depot_end/station node set. Required before any subtour
      method. Load `references/base-route-constraints.md` for the
      canonical notation and constraint block; mirror the variable names
      (`x[v,i,j]`, `START`, `END`, `vehicles`, `stations`) in the
      downstream method.
    outputs:
      - name: base-constraints-installed
        type: boolean
        description: Confirmation that depot-out, depot-in, flow-balance, and outgoing<=1 constraints are added per vehicle.
  - name: choose-method
    description: >
      Pick one subtour-elimination method based on instance size, solver
      behaviour, and pickup/dropoff semantics. Read
      `references/method-choice.md` for the decision table and heuristic.
      Default to MTZ. Upgrade to single-commodity flow if MTZ yields weak
      bounds. Use static DFJ only for n ≤ ~15. Use lazy/iterative DFJ when
      static MTZ is too weak and the solver permits iterative resolves.
      For pickup/dropoff rebalancing, never substitute physical truck load
      for the connectivity mechanism.
    inputs:
      - name: base-constraints-installed
        type: boolean
    outputs:
      - name: chosen-method
        type: string
        description: One of mtz, single-commodity-flow, static-dfj, lazy-iterative-dfj.
  - name: apply-method
    description: >
      Apply the chosen subtour-elimination method. Each option corresponds
      to a self-contained code template in `references/`. Splice the
      template into the model using the same variable names introduced in
      `add-base-route-constraints`.
    inputs:
      - name: chosen-method
        type: string
    outputs:
      - name: subtour-constraints-installed
        type: boolean
    one_of:
      - "mtz — load references/mtz.md and add order vars + MTZ inequalities per vehicle"
      - "single-commodity-flow — load references/single-commodity-flow.md and add artificial connectivity flow vars + balance/coupling constraints"
      - "static-dfj — load references/dfj-static.md and enumerate subset cuts over all 2<=|S|<n (tiny instances only)"
      - "lazy-iterative-dfj — load references/lazy-cuts.md, solve, detect station-only cycles in the incumbent, add violated DFJ cuts, repeat until no cuts are added"
  - name: validate-routes
    description: >
      After the solver returns an incumbent, reconstruct each vehicle's
      route by following selected arcs from START to END. Load
      `references/validation.md` for the `extract_route` template. Fail
      fast on disconnection, repeated stations, or missing depot
      endpoints. If validation fails, the chosen method was insufficient
      (e.g., MTZ LP relaxation accepted a fractional incumbent that
      rounded to a cycle) — strengthen the method (switch to flow or
      lazy DFJ) and re-solve.
    inputs:
      - name: subtour-constraints-installed
        type: boolean
    outputs:
      - name: routes-valid
        type: boolean
        description: True only if every vehicle's reconstructed route is a single depot-to-depot path with no repeated station and no disconnected cycle.

scenarios:
  - need: Bike-share rebalancing — multi-vehicle pickup/dropoff routing with depot start/end.
    context: >
      Each station has a positive or negative net rebalancing target.
      Vehicle load can both increase (pickup) and decrease (dropoff)
      along the route, so physical load is not monotonic and cannot serve
      as a connectivity flow.
    action: >
      Add base route constraints, then apply MTZ (default) or
      single-commodity artificial connectivity flow. Validate routes
      after solve.
    outcome: >
      Vehicles produce contiguous depot-to-depot paths with no
      station-only cycles, and the objective remains tight against the
      benchmark.
  - need: Small TSP benchmark (n ≤ 15) where correctness matters more than speed.
    action: >
      Use static DFJ enumeration as the baseline; cross-check against
      MTZ to confirm both yield the same optimal route.
    outcome: A correctness oracle for the larger lazy-cut implementation.
  - need: Larger VRP where MTZ produces weak LP bounds and the solver stalls.
    action: >
      Switch to lazy/iterative DFJ cuts — solve, detect station-only
      cycles via `station_cycles_without_start`, add violated cuts,
      re-solve until no cuts are added.
    outcome: Tighter relaxation and faster convergence than static MTZ at acceptable iteration cost.

anti_patterns:
  - Reusing physical vehicle load as the connectivity flow in a pickup/dropoff model. Load can decrease as well as increase and does not prove connectivity — use an artificial flow or MTZ instead.
  - Skipping the base degree/flow-balance constraints because "subtour cuts will fix it." Subtour methods assume matched in/out degree on every visited station; without it, the model is malformed.
  - Enumerating all DFJ subsets statically for n > ~15-18. Constraint count explodes; the solver chokes before subtour elimination matters.
  - Interpreting MTZ order variables as service times. They are artificial sequencing variables; treat them as such unless time is independently modelled.
  - Trusting "optimal" output without reconstructing routes. MTZ on its own can produce incumbents whose integer values still imply a cycle if base degree constraints were misspecified — always run `extract_route` and fail fast.
  - Forgetting to exclude `START`/`END` when detecting station-only cycles in lazy separation. A depot-anchored path is not a subtour; only station-only cycles should trigger a cut.
```
