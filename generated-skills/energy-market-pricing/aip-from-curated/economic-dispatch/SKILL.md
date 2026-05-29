---
name: economic-dispatch
description: "Generator economic dispatch and cost optimization for power systems. Use when minimizing generation costs, computing optimal generator setpoints, calculating operating margins, or working with MATPOWER-shaped generator cost functions. Supports optional operating-reserve co-optimization."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.10+, numpy, and cvxpy with the CLARABEL solver.
---

```yaml
purpose: >
  Solve generator economic dispatch on MATPOWER-shaped network data: minimize
  total polynomial generation cost subject to per-generator P_min/P_max limits
  and a system-wide power-balance constraint, with optional operating-reserve
  co-optimization (reserve capacity, output+reserve capacity coupling, and a
  system reserve requirement). Returns per-generator dispatch (MW), per-generator
  reserves (MW), totals, and the operating margin. Network line-flow limits are
  out of scope — compose with the dc-power-flow skill when branch constraints
  must be enforced.

trigger_when:
  - User asks to minimize generation cost or compute optimal generator setpoints.
  - Problem statement supplies MATPOWER-style `gen`, `gencost`, `bus`, and `baseMVA`.
  - Reserve co-optimization is requested (network data carries `reserve_capacity` and `reserve_requirement`).
  - Operating margin or remaining capacity headroom must be reported.

do_not_use_when:
  - Branch flow limits must bind — use dc-power-flow (DC-OPF) instead or compose the two.
  - Unit-commitment decisions (binary on/off, startup/shutdown costs) are required — this skill assumes all units are online.
  - AC effects (voltages, reactive power, losses) are in scope — this skill is DC, real-power only.

scope_and_approval: >
  Read-only computation. No external state mutation; the skill solves a convex
  optimization in-memory and returns a result dictionary. The caller is
  responsible for any downstream writes (saving dispatch.json, posting to a
  market interface, etc.).

steps:
  - name: parse-inputs
    description: >
      Extract MATPOWER arrays (`gen`, `gencost`, `bus`) and `baseMVA` from the
      provided network data. If the data carries `reserve_capacity` (per-generator
      MW vector) and `reserve_requirement` (scalar MW), pass both through to
      enable reserve co-optimization; otherwise leave them unset.
    outputs:
      - name: gens
        type: object
        description: MATPOWER generator array, shape (n_gen, >=10). Column 0 = bus, 8 = Pmax MW, 9 = Pmin MW.
      - name: gencost
        type: object
        description: MATPOWER gencost array, MODEL=2 (polynomial). NCOST at col 3, coefficients from col 4 (highest order first).
      - name: buses
        type: object
        description: MATPOWER bus array, shape (n_bus, >=3). Column 2 = real power demand (MW).
      - name: baseMVA
        type: float
      - name: reserve_capacity
        type: list[float]
        nullable: true
        description: Optional per-generator reserve cap r_bar (MW). Length must equal n_gen.
      - name: reserve_requirement
        type: float
        nullable: true
        description: Optional system-wide minimum total reserves R (MW).

  - name: solve-dispatch
    description: >
      Build and solve the convex economic-dispatch problem. Cost is polynomial
      per MATPOWER MODEL=2, handling NCOST in {0,1,2,3}. Variables Pg are
      per-unit on baseMVA; per-unit conversion and rounding happen inside the
      script. Reserves are co-optimized when both reserve inputs are supplied,
      otherwise reserves are reported as zero. Uses CLARABEL — robust on
      QP/SOCP forms where OSQP can fail on ill-conditioned instances.
    script: scripts/economic_dispatch.py
    inputs:
      - name: gens
        type: object
      - name: gencost
        type: object
      - name: buses
        type: object
      - name: baseMVA
        type: float
      - name: reserve_capacity
        type: list[float]
        nullable: true
      - name: reserve_requirement
        type: float
        nullable: true
    outputs:
      - name: generator_dispatch
        type: list[object]
        description: One dict per generator with `id`, `bus`, `output_MW`, `reserve_MW`, `pmax_MW`.
      - name: totals
        type: object
        description: "Keys: cost_dollars_per_hour, load_MW, generation_MW, reserve_MW, operating_margin_MW."
      - name: solver_status
        type: string
        description: cvxpy solver status. Treat anything outside {optimal, optimal_inaccurate} as failure.
      - name: reserves_enabled
        type: boolean

  - name: interpret-and-report
    description: >
      Verify solver status is `optimal` (or `optimal_inaccurate` if the user has
      explicitly accepted reduced precision). Report `generator_dispatch` and
      `totals` to the user in whatever shape the task requires (JSON file,
      printed table, API payload). If the task only requested a subset (e.g.,
      "cost" or "operating margin"), surface those fields directly rather than
      dumping the full result.
    inputs:
      - name: generator_dispatch
        type: list[object]
      - name: totals
        type: object
      - name: solver_status
        type: string

modes:
  - name: energy-only
    body: >
      Skip the reserve inputs. The script omits Rg and the reserve requirement
      constraint; `reserve_MW` in the output is zero and `operating_margin_MW`
      reduces to sum(Pmax - Pg).
  - name: energy-and-reserves
    body: >
      Provide both `reserve_capacity` (per-generator MW vector, length n_gen)
      and `reserve_requirement` (system MW). The script adds Rg >= 0,
      Rg[i] <= r_bar[i], Pg[i]*baseMVA + Rg[i] <= Pmax[i], and sum(Rg) >= R.

integrations:
  - partner: dc-power-flow
    body: >
      Economic dispatch enforces a single system-wide power-balance equation.
      For network-aware dispatch — nodal balance, line limits via PTDF or DC
      power flow — replace the system balance step with the DC-OPF formulation
      from the dc-power-flow skill while keeping this skill's cost model and
      reserve formulation.

scenarios:
  - need: Energy-only minimum-cost dispatch on a 5-bus MATPOWER case.
    context: Network data carries `gen`, `gencost`, `bus`, `baseMVA`; no reserve fields.
    action: Call `solve_economic_dispatch(gens, gencost, buses, baseMVA)`; report `totals.cost_dollars_per_hour` and `generator_dispatch`.
    outcome: Cost-minimizing setpoints honoring P_min/P_max and total load.

  - need: Compute operating reserve schedule alongside energy.
    context: Network data includes per-generator `reserve_capacity` and a system `reserve_requirement`.
    action: Pass both reserve fields. The solver co-optimizes Pg and Rg; output includes per-generator `reserve_MW` and `totals.reserve_MW`.
    outcome: Feasible joint energy+reserve schedule; total reserves >= R; for each generator, output+reserve <= Pmax.

  - need: Report uncommitted operating margin only.
    context: User asks for system headroom, not the full dispatch.
    action: Solve dispatch, then report `totals.operating_margin_MW` (sum of Pmax - Pg - Rg).
    outcome: Single scalar surfaced to the user without dumping the full dispatch payload.

anti_patterns:
  - Hard-coding NCOST=3. The MATPOWER spec allows NCOST in {1,2,3} — the script branches on it. Do not assume quadratic.
  - Mixing units. Pg is per-unit on baseMVA; Pmin/Pmax (`gens[:, 9]`, `gens[:, 8]`) and load (`buses[:, 2]`) are MW; reserves are MW. The script handles conversion — do not pre-scale.
  - Using OSQP for ill-conditioned QPs. CLARABEL is the default for this skill; OSQP may report `solved_inaccurate` or fail outright on DC-OPF-with-reserves instances.
  - Adding line-flow constraints here. That belongs in dc-power-flow. Composing the two is fine; silently extending this skill is not.
  - Treating `operating_margin_MW` as spinning reserve. It is the uncommitted headroom (Pmax - Pg - Rg), not the reserve schedule itself.
  - Reading bus number as a 0-based index. Bus numbers (column 0 of `gens` and `buses`) are 1-indexed; build a `bus_num -> idx` map when joining across arrays.
```
