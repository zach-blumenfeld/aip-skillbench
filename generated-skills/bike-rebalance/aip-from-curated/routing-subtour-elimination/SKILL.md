---
name: routing-subtour-elimination
description: Subtour-elimination methods for TSP, VRP, pickup/dropoff routing, and routing MIPs with binary arc variables. Use when route-continuity constraints may permit disconnected cycles and the model needs MTZ constraints, flow-based connectivity constraints, DFJ subset cuts, or lazy/iterative subtour cuts.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Designed to compose with a PySCIPOpt-backed routing MIP. The helper scripts import pyscipopt lazily; install it before invoking them.
---

```yaml
purpose: >
  Forbid disconnected station-only cycles in routing MIPs whose decisions
  are binary arc variables `x[v, i, j]`. Degree and continuity
  constraints alone permit a vehicle to have one depot-to-depot path AND
  a separate closed cycle among stations — both feasible, both wrong.
  This skill installs the canonical depot-start / depot-end / arc /
  binary-arc-variable notation, adds the base degree+continuity
  constraints, picks one subtour-elimination family from a four-method
  catalog (MTZ order constraints, single-commodity artificial flow,
  static DFJ subset cuts, or iterative DFJ cut separation), applies it,
  and validates the extracted routes by walking the successor map. The
  method choice is encoded as a structured recommender so the agent
  does not redrift the curated thresholds.

trigger_when:
  - The routing MIP has binary arc variables `x[v, i, j]` (or equivalent).
  - The problem is TSP, VRP, pickup/dropoff routing, or any variant where each vehicle must trace a single connected depot-to-depot path.
  - Degree and continuity constraints are present but disconnected station-only cycles are still feasible.
  - A previous solve produced a "route" containing an unreachable cycle disjoint from the depot.
  - The agent is composing a routing model and needs to choose between MTZ, flow-based, DFJ, or lazy/iterative subtour elimination.

do_not_use_when:
  - The model is not a routing MIP (no arc variables, no vehicles, no successor relationship).
  - The routing problem is so small (n <= 3) that subtour elimination is structurally impossible.
  - The model already uses set-partitioning / column-generation formulations where subtours cannot arise.

scope_and_approval: >
  All operations are in-process model edits — adding variables,
  constraints, and (for lazy separation) iterating SCIP solves.
  No filesystem writes, no network calls. Safe to apply without
  prompting; the route extractor at the end is the guardrail against
  silently shipping a disconnected solution.

steps:
  - name: confirm-binary-arc-model
    description: >
      Verify the problem really needs subtour elimination. Required
      pre-conditions: binary arc variables `x[v, i, j]`, at least one
      vehicle, at least two stations whose visit order is not already
      pinned, and the agent intends to use degree+continuity (not
      set-partitioning) as the route structure. If any pre-condition
      fails, stop and re-plan with the user instead of forcing a
      formulation onto a problem that does not need it.

  - name: establish-base-notation
    description: >
      Adopt the canonical notation — `DEPOT_START`, `DEPOT_END`,
      `vehicles`, `stations`, `arcs`, `x[v, i, j]`. Build the arc set
      via `scripts/route_setup.py::build_arc_set` (excludes self-loops
      and the direct START -> END edge) and add the binary variables
      via `scripts/route_setup.py::add_arc_variables`. The downstream
      helpers assume this exact shape; if the model deviates, switch to
      `references/methods.md` and re-derive each method by hand
      instead.
    script: scripts/route_setup.py
    inputs:
      - name: vehicles
        type: list[object]
        description: Vehicle identifiers (range of K).
      - name: stations
        type: list[object]
        description: Station identifiers (range of n or string ids).
    outputs:
      - name: x
        type: object
        description: Binary arc variables keyed by (vehicle, from_node, to_node).
      - name: arcs
        type: list[object]
        description: Canonical arc set used by every downstream step.

  - name: add-base-route-constraints
    description: >
      Add degree + continuity + at-most-one-visit per (vehicle,
      station) via `scripts/route_setup.py::add_base_route_constraints`.
      Subtour elimination assumes these constraints are already present;
      adding any of the four methods on top of an unbalanced model
      produces nonsense. Read `references/notation.md` § Required base
      route constraints if you need to confirm the exact set.
    script: scripts/route_setup.py
    depends_on: [establish-base-notation]
    inputs:
      - name: x
        type: object

  - name: select-subtour-method
    description: >
      Pick one of mtz / single-commodity-flow / static-dfj /
      lazy-separation. Use `scripts/select_method.py::recommend_method`
      with structured problem features (`n_stations`, `n_vehicles`,
      `optional_visits`, `memory_tight`, `debug_baseline`,
      `weak_incumbents`). The recommender returns
      `MethodRecommendation(method, rationale)`; override the
      recommendation only with a written reason (e.g., solver-specific
      callback support not visible to the script).
    script: scripts/select_method.py
    inputs:
      - name: problem_features
        type: object
        description: n_stations, n_vehicles, optional_visits, memory_tight, debug_baseline, weak_incumbents.
    outputs:
      - name: method
        type: string
        description: One of mtz / single-commodity-flow / static-dfj / lazy-separation.
      - name: rationale
        type: string
        description: One-line reason for the choice — preserve for debug logs and post-mortems.

  - name: apply-subtour-elimination
    description: >
      Apply exactly ONE subtour-elimination family. Stacking two adds
      redundant constraints and slows the solve. For mtz / single-flow
      / static-dfj, call the matching function in
      `scripts/subtour_constraints.py`. For lazy-separation, defer to
      `scripts/lazy_separation.py::iterative_subtour_cuts`, which
      drives the solve-detect-cut loop itself.
    depends_on: [add-base-route-constraints, select-subtour-method]
    inputs:
      - name: x
        type: object
      - name: arcs
        type: list[object]
      - name: method
        type: string
    one_of:
      - mtz — scripts/subtour_constraints.py::add_mtz_constraints
      - single-commodity-flow — scripts/subtour_constraints.py::add_single_commodity_flow
      - static-dfj — scripts/subtour_constraints.py::add_static_dfj_cuts (n <= 18; raises otherwise)
      - lazy-separation — scripts/lazy_separation.py::iterative_subtour_cuts (drives the solve loop)
    outputs:
      - name: subtour_artifacts
        type: object
        description: Method-specific extras (e.g., MTZ order variables or single-commodity flow variables) returned for debugging.

  - name: extract-and-validate-routes
    description: >
      Reconstruct each vehicle's ordered route by walking the successor
      map from DEPOT_START to DEPOT_END via
      `scripts/route_extraction.py::extract_all_routes`. The script
      raises on disconnection, repeated stations, or missing endpoints
      — the curated source's fail-fast rule. SCIP feasibility is
      necessary but NOT sufficient; this walk is the final guardrail
      against shipping a "route" with an unreachable cycle.
    script: scripts/route_extraction.py
    depends_on: [apply-subtour-elimination]
    inputs:
      - name: x
        type: object
      - name: arcs
        type: list[object]
      - name: vehicles
        type: list[object]
    outputs:
      - name: routes
        type: object
        description: Dict {vehicle -> ordered list [DEPOT_START, ..., DEPOT_END]} ready for downstream cost/load checks.

modes:
  - name: fresh-model
    body: >
      Building a routing MIP from scratch. Start at
      `establish-base-notation`, then walk every step in order. Load
      `references/notation.md` once before adding variables so the
      naming convention matches the helper scripts.
  - name: retrofit-existing-model
    body: >
      The model already exists but produces solutions with disconnected
      cycles. Skip `establish-base-notation` and
      `add-base-route-constraints`; if the existing variable shape
      matches the canonical x[v, i, j], jump straight to
      `select-subtour-method`. If the shape differs, load
      `references/methods.md` and re-derive the chosen family against
      the existing variables instead of forcing the helper scripts.
  - name: pickup-dropoff
    body: >
      Pickup/dropoff rebalancing (e.g., bikes between stations). Start
      with MTZ or single-commodity flow — do NOT try to use physical
      truck load as the connectivity proof. Load can rise and fall
      along the route, which is not enough to forbid disconnected
      cycles. The connectivity flow in `add_single_commodity_flow` is
      a separate artificial flow for exactly this reason.

scenarios:
  - need: TSP-like single-vehicle route over ~10 stations for a benchmark task.
    context: One vehicle, one depot, every station visited exactly once. Solver is PySCIPOpt and the agent wants the strongest static formulation as a sanity baseline.
    action: Call `recommend_method(n_stations=10, debug_baseline=True)` -> static-dfj. Apply via `add_static_dfj_cuts` (n=10 is under the cap). Validate with `extract_route`.
    outcome: Strongest static formulation; clean reference solution to compare other methods against.
  - need: VRP with ~40 stations, multiple vehicles, no callbacks available.
    context: PySCIPOpt without convenient lazy callback plumbing. Memory is comfortable. No optional visits.
    action: Call `recommend_method(n_stations=40, n_vehicles=4)` -> single-commodity-flow. Apply via `add_single_commodity_flow`. Solve once. Walk routes via `extract_all_routes`.
    outcome: Stronger LP relaxation than MTZ at modest variable cost; single solve, no iterative loop.
  - need: Bike-rebalance over ~60 stations, pickup AND dropoff loads, weak MTZ incumbents in a prior run.
    context: Previously used MTZ; bound stayed loose and the solve ran out of time. The model has separate physical load variables already.
    action: Call `recommend_method(n_stations=60, weak_incumbents=True)` -> lazy-separation. Switch to `iterative_subtour_cuts(...)`. Confirm physical load is NOT reused as the connectivity proof.
    outcome: Adds only the DFJ cuts the incumbents need; converges in a handful of resolves on most instances.
  - need: Tiny 5-station debug instance to test the validator path.
    context: Want a deliberately-broken solve (no subtour cuts at all) to confirm `extract_route` raises on a disconnected cycle.
    action: Skip `apply-subtour-elimination`. Solve. Call `extract_route` — it raises `route disconnected at ...` or `cycle detected at ...` if the model misbehaved.
    outcome: Validator path exercised; downstream pipelines fail fast on disconnection instead of silently shipping a bad answer.

integrations:
  - partner: scip-opt skill
    body: >
      This skill composes on top of a model the `scip-opt` skill is
      building. Use `scip-opt` for the surrounding MIP scaffolding
      (variables, hard / soft constraints, objective, solve, validate),
      and this skill for the specific subtour-elimination piece. The
      helper scripts here assume PySCIPOpt is already importable —
      `scip-opt`'s `check_pyscipopt.py` is the right pre-flight check.
  - partner: problem-specific cost / load validator
    body: >
      `extract-and-validate-routes` only proves the routes are
      well-formed — not that loads, capacities, and objective
      components agree. Pair with the calling task's own validator
      (e.g., bike-rebalance reconciles per-station pickup / dropoff
      counts and inventory targets) to close the rest of the
      correctness loop.

anti_patterns:
  - Building a routing model with degree and continuity constraints only and shipping it. Disconnected station-only cycles satisfy both rules; you will get nonsense routes. Always pair with one of MTZ / flow / DFJ / lazy DFJ.
  - Using physical truck load as the subtour-elimination flow in a pickup/dropoff model. Physical load can rise and fall along the route, so it cannot prove connectivity. Use a separate artificial `f[v, i, j]` flow.
  - Stacking multiple subtour-elimination families on the same model. The constraints overlap and the solver wastes time on redundant cuts. Pick one.
  - Enumerating static DFJ on more than ~18 stations. The constraint count is exponential. `add_static_dfj_cuts` raises by default — override only with explicit `max_n=`.
  - Forgetting `model.freeTransform()` before adding cuts during the iterative lazy-separation loop. SCIP silently drops the cut and the next iteration loops on the same subtour. `iterative_subtour_cuts` calls it for you.
  - Reading binary arc values as `int(model.getVal(x[v, i, j])) == 1`. SCIP returns floats; use the 0.5 threshold via `selected_arcs` / `selected_arcs_for_vehicle`.
  - Interpreting MTZ order variables as service times. They are artificial. If service times matter, model them explicitly.
  - Treating SCIP feasibility as proof of a valid route. Always walk the successor map via `extract_route` — disconnection, revisits, and missing endpoints all surface there before the route reaches downstream code.
```
