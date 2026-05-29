---
name: economic-dispatch
description: "Generator economic dispatch and cost optimization for MATPOWER-format power systems. Use when minimizing generation cost, computing optimal generator setpoints, co-optimizing spinning reserves with capacity coupling, calculating operating margin, or formatting dispatch report fields. Provides MATPOWER array layout, CVXPY problem-building helpers (cost objective with variable NCOST, generator limits, reserve constraints), CLARABEL solve, and output formatters. Composes with the dc-power-flow skill for DC-OPF nodal balance and branch limits."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Solve generator economic dispatch on a MATPOWER-format network: minimize
  total $/hr generation cost subject to generator Pmin/Pmax limits, power
  balance, and (optionally) spinning-reserve requirements with standard
  capacity coupling. Provides MATPOWER array indexing rules, a CVXPY
  cost-objective builder that handles variable NCOST per generator, reserve
  variables and constraints, a CLARABEL-default solve, and helpers that
  format the `generator_dispatch`, `totals`, and `operating_margin_MW`
  report fields expected by grid-dispatch tasks.

trigger_when:
  - Computing optimal generator setpoints to minimize $/hr cost on a MATPOWER network.
  - Building a CVXPY cost expression from a `gencost` array (especially with mixed NCOST).
  - Adding spinning-reserve variables with capacity coupling `Pg + Rg ≤ Pmax`.
  - Calculating an operating margin or dispatch totals for a report.
  - Solving DC-OPF with reserves — compose with `dc-power-flow` for the network.
  - User asks for dispatch, generation cost minimization, generator scheduling, or reserves.

do_not_use_when:
  - The task is unit commitment with binary on/off decisions — this skill assumes continuous Pg.
  - AC power flow detail (reactive power, voltages) is required — this skill targets the DC linearization.
  - The cost is purely piecewise-linear (gencost MODEL=1) without polynomial form — extend `build_cost_objective` first.

scope_and_approval: >
  Read-only on inputs; no side effects. The skill builds and solves a convex
  optimization problem in-process and returns dispatch values plus report
  fields. The caller decides how to persist results (typically writing
  `report.json` per the task instructions).

steps:
  - name: load-network
    description: Read `network.json` (MATPOWER format) and lift baseMVA, bus, gen, gencost, branch, and reserve arrays into numpy arrays.
    outputs:
      - name: network-data
        type: object
        description: dict with baseMVA (float), buses, gens, gencost, branches (numpy arrays), and reserve_capacity / reserve_requirement when present.

  - name: build-bus-index
    description: Map non-contiguous MATPOWER bus numbers to numpy row indices; never use a bus number as an array index directly.
    script: scripts/economic_dispatch.py
    inputs:
      - name: network-data
        type: object
    outputs:
      - name: bus-num-to-idx
        type: object
        description: dict[int, int] mapping bus number → row index in `buses`.

  - name: declare-variables
    description: Declare `Pg = cp.Variable(n_gen)` (per-unit). If reserves are required, also declare `Rg = cp.Variable(n_gen)` (MW).
    inputs:
      - name: network-data
        type: object
    outputs:
      - name: Pg
        type: object
        description: cvxpy.Variable for generator real-power output in per-unit.
      - name: Rg
        type: object
        nullable: true
        description: cvxpy.Variable for generator reserve in MW. Omit when no reserve_requirement.

  - name: build-cost
    description: >
      Build CVXPY cost expression that handles variable NCOST per generator
      (quadratic NCOST=3, linear NCOST=2, constant NCOST=1). Cost is $/hr;
      Pg is converted MW internally via `Pg * baseMVA`.
    script: scripts/economic_dispatch.py
    inputs:
      - name: network-data
        type: object
      - name: Pg
        type: object
    outputs:
      - name: cost-expr
        type: object
        description: CVXPY expression suitable for `cp.Minimize(cost_expr)`.

  - name: build-generator-limits
    description: Add `Pmin ≤ Pg ≤ Pmax` for every generator, converting MW → per-unit by dividing by baseMVA.
    script: scripts/economic_dispatch.py
    inputs:
      - name: network-data
        type: object
      - name: Pg
        type: object
    outputs:
      - name: generator-constraints
        type: list[object]
        description: List of CVXPY constraints.

  - name: build-power-balance
    description: >
      One of two paths. (a) Single-bus or network-out-of-scope:
      `cp.sum(Pg) == total_load_pu` via the helper. (b) DC-OPF with
      transmission: replace with the nodal balance from the `dc-power-flow`
      skill (P_inj = B_bus · θ, with branch flow limits). See Integrations.
    script: scripts/economic_dispatch.py
    inputs:
      - name: network-data
        type: object
      - name: Pg
        type: object
    outputs:
      - name: balance-constraints
        type: list[object]
    one_of:
      - simple aggregate balance (single bus / no network)
      - DC-OPF nodal balance from dc-power-flow skill

  - name: build-reserves
    description: >
      If `reserve_requirement` and `reserve_capacity` are present, add
      Rg ≥ 0, per-generator caps `Rg ≤ reserve_capacity`, capacity coupling
      `Pg_MW + Rg ≤ Pmax`, and system floor `sum(Rg) ≥ reserve_requirement`.
      Skip this step when no reserves are required.
    script: scripts/economic_dispatch.py
    inputs:
      - name: network-data
        type: object
      - name: Pg
        type: object
      - name: Rg
        type: object
    outputs:
      - name: reserve-constraints
        type: list[object]

  - name: solve
    description: >
      Solve `cp.Problem(cp.Minimize(cost), constraints)` with CLARABEL. Fall
      back to ECOS then SCS per `references/solver-selection.md` if status is
      not optimal. OSQP may fail on DC-OPF + reserves; do not use it.
    script: scripts/economic_dispatch.py
    inputs:
      - name: cost-expr
        type: object
      - name: generator-constraints
        type: list[object]
      - name: balance-constraints
        type: list[object]
      - name: reserve-constraints
        type: list[object]
    outputs:
      - name: solved-problem
        type: object
        description: cvxpy.Problem with prob.value, Pg.value, Rg.value populated.

  - name: format-output
    description: >
      Build `generator_dispatch` (per-generator id/bus/output_MW/reserve_MW/pmax_MW),
      `totals` (cost_dollars_per_hour, load_MW, generation_MW, reserve_MW), and
      `operating_margin_MW` (= Σ(Pmax_i − Pg_i_MW − Rg_i)) from the solved
      problem. These slot directly into the task's `report.json` schema.
    script: scripts/economic_dispatch.py
    inputs:
      - name: solved-problem
        type: object
      - name: network-data
        type: object
    outputs:
      - name: generator-dispatch
        type: list[object]
      - name: totals
        type: object
      - name: operating-margin-MW
        type: float

integrations:
  - partner: dc-power-flow
    body: >
      When transmission topology is in scope (the common case for the
      grid-dispatch-operator task), replace `build_simple_power_balance` with
      the DC-OPF nodal balance from the `dc-power-flow` skill: bus injections
      P_inj = (generation at bus) − (load at bus); P_inj = B_bus · θ with a
      reference angle; and branch limits |Pf| ≤ rateA. Cost, generator
      limits, and reserves from this skill compose unchanged — the only
      change is which constraint enforces conservation. The `most_loaded_lines`
      report field comes from the dc-power-flow branch flow values, not from
      this skill.
  - partner: power-flow-data
    body: >
      Use `power-flow-data` to parse and validate the MATPOWER `network.json`
      into numpy arrays before invoking this skill's `load-network` step.

scenarios:
  - need: Minimize cost ignoring transmission (single-bus or aggregate balance), no reserves.
    action: build_cost_objective + build_generator_limit_constraints + build_simple_power_balance, then solve_problem(CLARABEL).
    outcome: Returns Pg per generator and total $/hr cost.
  - need: Full grid-dispatch-operator task — DC-OPF with reserves and transmission limits.
    context: dc-power-flow skill loaded for B-matrix and PTDF; reserve_capacity and reserve_requirement present in network.json.
    action: >
      Compose this skill's cost + generator + reserve constraints with
      dc-power-flow's nodal balance and branch flow limits. Solve with
      CLARABEL. Use format_generator_dispatch, compute_totals, and
      compute_operating_margin for the report; take most_loaded_lines from
      dc-power-flow's branch-flow output.
    outcome: report.json with dispatch, totals, top-3 most-loaded lines, and operating_margin_MW.
  - need: gencost mixes quadratic and linear cost rows.
    action: build_cost_objective branches on NCOST per row — no caller-side preprocessing needed.
    outcome: Single cost expression covering all generators.

anti_patterns:
  - Treating bus numbers as 0-based row indices — MATPOWER bus numbers are 1-indexed and may be non-contiguous; always go through bus_num_to_idx.
  - Hard-coding NCOST=3 — handle NCOST=2 (linear) and the rare NCOST=1 (constant) cases. Use build_cost_objective rather than re-implementing.
  - Forgetting the capacity-coupling constraint `Pg_MW + Rg ≤ Pmax` — Rg ≤ reserve_capacity alone oversubscribes generator capacity.
  - Mixing MW and per-unit silently — multiply Pg by baseMVA before combining with cost coefficients sized in $/MW. Rg is already in MW.
  - Solving with default OSQP for DC-OPF + reserves — CLARABEL is the default; see references/solver-selection.md for fallbacks.
  - Reporting operating margin as `total_load - total_gen` — it is `Σ(Pmax − Pg − Rg)`, the uncommitted headroom, not the energy surplus.
  - Replacing the cost objective when only the balance constraint changes — composing with dc-power-flow only swaps the balance step.
```
