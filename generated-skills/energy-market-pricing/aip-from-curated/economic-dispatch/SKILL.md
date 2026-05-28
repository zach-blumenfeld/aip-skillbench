---
name: economic-dispatch
description: "Generator economic dispatch and cost optimization for power systems. Use when minimizing generation costs, computing optimal generator setpoints, calculating operating margins, or working with generator cost functions."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.10+, numpy, and cvxpy with the CLARABEL solver. Pairs with the dc-power-flow skill for network-constrained DC-OPF.
---

```yaml
purpose: >
  Build and solve economic dispatch on MATPOWER-format power systems:
  construct the generator cost objective (linear, quadratic, or constant
  per generator), generator output limits, system or nodal power balance,
  optional spinning-reserve co-optimization with standard capacity
  coupling, and operating-margin reporting. Provides composable building
  blocks that wire into a larger DC-OPF — see the dc-power-flow skill for
  nodal balance, line flows, and the duals used to extract LMPs.

trigger_when:
  - Minimizing total generation cost while meeting demand and generator limits.
  - Computing optimal generator setpoints (Pg) for a snapshot dispatch.
  - Working with MATPOWER `gen` and `gencost` arrays.
  - Adding spinning-reserve co-optimization with standard capacity coupling.
  - Computing operating margin (uncommitted headroom) after dispatch.
  - Forming the energy-cost objective inside a DC-OPF with network constraints.

do_not_use_when:
  - The network's line flows or bus angles must be modeled — use the
    dc-power-flow skill for the network part and compose this skill's
    cost and limits with it.
  - The problem is unit commitment with binary on/off decisions. This
    skill handles only continuous dispatch.

scope_and_approval: >
  Read-only with respect to the supplied network.json — the helpers
  never mutate it. All side effects are confined to the agent's local
  Python session. Safe to run without approval.

steps:
  - name: load-network
    description: >
      Load MATPOWER network.json and bundle buses, gens, gencost,
      baseMVA, dimensions, and the bus-number → index mapping that
      handles non-contiguous bus numbers. Calls
      `dispatch_helpers.load_matpower`.
    script: scripts/dispatch_helpers.py
    inputs:
      - name: network_path
        type: string
        description: Path to the MATPOWER-format network JSON file.
    outputs:
      - name: net
        type: object
        description: >
          Dict with keys data, buses, gens, gencost, baseMVA, n_bus,
          n_gen, bus_num_to_idx, gen_bus_idx.

  - name: declare-variables
    description: >
      Allocate the dispatch decision variable `Pg = cp.Variable(n_gen)`
      in per-unit. When reserves are required, also allocate
      `Rg = cp.Variable(n_gen)` in MW (reserves are conventionally MW).
      Otherwise pass `Rg_value = np.zeros(n_gen)` downstream.
    inputs:
      - name: n_gen
        type: integer
      - name: reserves_required
        type: boolean
        description: True when the network supplies reserve_capacity and reserve_requirement.
    outputs:
      - name: Pg
        type: object
        description: cvxpy Variable for generator outputs in per-unit.
      - name: Rg
        type: object
        nullable: true
        description: cvxpy Variable for generator reserves in MW; null when reserves are not modeled.

  - name: build-cost-objective
    description: >
      Build the cvxpy cost expression from the gencost array, branching
      on per-generator NCOST (quadratic / linear / constant). Read
      `references/cost-functions.md` when you need the full MATPOWER
      polynomial-type-2 format or marginal-cost identities. Calls
      `dispatch_helpers.build_cost`.
    script: scripts/dispatch_helpers.py
    inputs:
      - name: Pg
        type: object
      - name: gencost
        type: object
      - name: baseMVA
        type: float
      - name: n_gen
        type: integer
    outputs:
      - name: cost
        type: object
        description: cvxpy scalar expression in $/hr.

  - name: add-generator-limits
    description: >
      Append `Pmin <= Pg <= Pmax` constraints in per-unit. Reads MW
      limits from `gens[:, 9]` (Pmin) and `gens[:, 8]` (Pmax) and
      divides by baseMVA. Calls `dispatch_helpers.generator_limit_constraints`.
    script: scripts/dispatch_helpers.py
    inputs:
      - name: Pg
        type: object
      - name: gens
        type: object
      - name: baseMVA
        type: float
      - name: n_gen
        type: integer
    outputs:
      - name: gen_limit_constraints
        type: list[object]

  - name: add-power-balance
    description: >
      Pick exactly one. `system_balance` enforces `sum(Pg) == total_load`
      (per-unit) — use only when there are no network constraints. For
      DC-OPF, use the nodal balance supplied by the dc-power-flow skill
      and DO NOT also add `system_balance` (the system constraint is the
      sum of the nodal ones; adding both makes the LP rank-deficient and
      breaks LMP extraction). System-level path calls
      `dispatch_helpers.system_power_balance`.
    script: scripts/dispatch_helpers.py
    one_of:
      - system_balance
      - nodal_balance_from_dc_power_flow_skill
    inputs:
      - name: Pg
        type: object
      - name: buses
        type: object
      - name: baseMVA
        type: float
      - name: n_bus
        type: integer
    outputs:
      - name: balance_constraints
        type: list[object]

  - name: add-reserve-cooptimization
    description: >
      Optional. When the network supplies `reserve_capacity` (per-gen MW)
      and `reserve_requirement` (system MW), add `Rg >= 0`, the per-gen
      cap, the capacity coupling `Pg_MW[i] + Rg[i] <= Pmax[i]`, and the
      system requirement `sum(Rg) >= reserve_requirement`. Returns the
      constraint list AND the system-reserve constraint object — keep a
      handle to the latter so its dual (the reserve MCP in $/MWh) can be
      read after solve. Calls `dispatch_helpers.reserve_cooptimization`.
    script: scripts/dispatch_helpers.py
    inputs:
      - name: Pg
        type: object
      - name: Rg
        type: object
      - name: gens
        type: object
      - name: reserve_capacity
        type: object
        description: numpy array, per-generator reserve cap in MW.
      - name: reserve_requirement
        type: float
        description: System-wide minimum total reserves in MW.
      - name: baseMVA
        type: float
      - name: n_gen
        type: integer
    outputs:
      - name: reserve_constraints
        type: list[object]
      - name: system_reserve_constraint
        type: object
        description: The `sum(Rg) >= reserve_requirement` constraint object; `.dual_value` is the reserve MCP in $/MWh.

  - name: solve
    description: >
      Build `cp.Problem(cp.Minimize(cost), constraints)` and solve with
      CLARABEL. Check `prob.status == 'optimal'` before reading values;
      do not silently fall back to a different solver on failure —
      investigate (typical causes: missing constraint, unit-mismatch,
      infeasible reserve requirement). Calls `dispatch_helpers.solve_dispatch`.
    script: scripts/dispatch_helpers.py
    inputs:
      - name: cost
        type: object
      - name: constraints
        type: list[object]
    outputs:
      - name: prob
        type: object
        description: Solved cvxpy Problem; `.value` is the objective, per-constraint `.dual_value` gives the multipliers used for LMPs and the reserve MCP.

  - name: compute-operating-margin
    description: >
      After solve, compute `sum(Pmax_i - Pg_i - Rg_i)` in MW across
      generators — uncommitted system headroom beyond both scheduled
      energy and reserves. When reserves were not modeled, pass
      `Rg_value = np.zeros(n_gen)`. Calls `dispatch_helpers.operating_margin_MW`.
    script: scripts/dispatch_helpers.py
    inputs:
      - name: Pg_value
        type: object
      - name: Rg_value
        type: object
      - name: gens
        type: object
      - name: baseMVA
        type: float
      - name: n_gen
        type: integer
    outputs:
      - name: operating_margin_MW
        type: float

  - name: format-output
    description: >
      Build the per-generator dispatch list (id, bus, output_MW,
      reserve_MW, pmax_MW) and the system totals dict
      (cost_dollars_per_hour, load_MW, generation_MW, reserve_MW), all
      rounded to 2 decimal places. Calls `dispatch_helpers.format_dispatch`
      and `dispatch_helpers.format_totals`.
    script: scripts/dispatch_helpers.py
    inputs:
      - name: prob
        type: object
      - name: Pg_value
        type: object
      - name: Rg_value
        type: object
      - name: buses
        type: object
      - name: gens
        type: object
      - name: baseMVA
        type: float
      - name: n_bus
        type: integer
      - name: n_gen
        type: integer
    outputs:
      - name: generator_dispatch
        type: list[object]
      - name: totals
        type: object

integrations:
  - partner: dc-power-flow
    body: >
      For DC-OPF, this skill supplies the cost objective, generator
      limits, and reserve co-optimization; the dc-power-flow skill
      supplies the line-flow formulation (B matrix, PTDFs or angle
      variables), per-line thermal limits, and the nodal power-balance
      constraints. Compose them by sharing the same `Pg` cvxpy variable
      and the same constraints list, then solve one `cvxpy.Problem`
      with CLARABEL. After solve, LMPs come from the duals of the
      dc-power-flow nodal-balance constraints; the reserve MCP comes
      from the dual of THIS skill's `system_reserve_constraint`. A line
      is "binding" when |flow| / limit >= 0.99.

scenarios:
  - need: Snapshot economic dispatch with no network constraints — minimize cost subject to generator limits and total balance.
    action: >
      load-network → declare-variables (no Rg) → build-cost-objective →
      add-generator-limits → add-power-balance (system_balance) → solve
      → compute-operating-margin (pass Rg_value = zeros) → format-output.
    outcome: Optimal Pg in MW per generator, total system cost in $/hr, and an operating-margin number.

  - need: DC-OPF with spinning-reserve co-optimization for a market-clearing run that reports LMPs and reserve MCP.
    context: >
      network.json supplies `reserve_capacity` (per generator, MW) and a
      scalar `reserve_requirement` (MW). Network branches enforce thermal
      limits.
    action: >
      load-network → declare-variables (with Rg) → build-cost-objective
      → add-generator-limits → add-reserve-cooptimization (keep the
      system_reserve_constraint handle) → add-power-balance via
      dc-power-flow's nodal constraints (keep handles for LMP duals) +
      add line-flow limits from dc-power-flow → solve (CLARABEL,
      verify optimal) → compute-operating-margin → format-output.
      Read LMPs from the nodal-balance dual_values; read reserve MCP
      from system_reserve_constraint.dual_value; flag any branch with
      flow/limit >= 0.99 as binding.
    outcome: Cleared energy + reserves, per-bus LMPs, system reserve MCP, binding-line list, and totals — the building blocks of a market report.

  - need: Counterfactual "what if we raise this line's thermal limit by 20%?" comparison.
    context: Same model and data; only the branch limit for the one line changes between runs.
    action: >
      Run the DC-OPF scenario above once with the base limit and once
      with the inflated limit, reusing the same load-network result.
      Diff the two totals and per-bus LMPs to produce the impact
      analysis.
    outcome: Cost reduction in $/hr, the three buses with the largest LMP drop, and whether the targeted line is still binding after relaxation.

anti_patterns:
  - Using OSQP for DC-OPF with reserves. It frequently fails on ill-conditioned cases; prefer CLARABEL and investigate non-optimal status rather than swapping solvers.
  - "Assuming contiguous bus numbering. MATPOWER bus numbers may be sparse; always build `bus_num_to_idx = {int(buses[i, 0]): i ...}` and map generator buses through it."
  - Forgetting MW ↔ per-unit conversion. `Pg` is per-unit; `gens[:, 8]` / `gens[:, 9]` are MW; multiply `Pg` by `baseMVA` whenever it appears next to a MW quantity (reserve capacity coupling, MW reports).
  - Treating the gencost array as uniformly quadratic. Always read `NCOST = gencost[i, 3]` per row and branch on 3, 2, or 1.
  - Adding both system-level `sum(Pg) == total_load` and the dc-power-flow nodal balance. Use exactly one; doubling makes the LP rank-deficient and LMP duals unreliable.
  - Computing "operating margin" as `Pmax − Pg` only. The skill defines it as uncommitted headroom — also subtract Rg.
  - Forgetting to keep a handle to the `system_reserve_constraint` returned by `reserve_cooptimization`. Without it, the reserve MCP cannot be read after solve.
```
