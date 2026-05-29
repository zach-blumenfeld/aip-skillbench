---
name: economic-dispatch
description: "Generator economic dispatch and reserve co-optimization for MATPOWER-format power systems. Use when minimizing total generation cost, computing optimal generator setpoints (with or without spinning reserves), enforcing capacity coupling (p+r<=Pmax), calculating operating margin (uncommitted headroom), parsing MATPOWER polynomial gencost arrays, or formatting per-generator dispatch output."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Cost-side and reserve-side modeling for economic dispatch on MATPOWER-format
  networks. Owns: parsing variable-NCOST polynomial gencost arrays into a cvxpy
  objective, generator min/max bounds, reserve variables with capacity coupling,
  and assembling the per-generator dispatch report (output_MW, reserve_MW,
  pmax_MW, totals, operating margin). Pairs with `dc-power-flow` for nodal power
  balance, slack-bus, line susceptance, and thermal limits; with `power-flow-data`
  for loading `network.json` into numpy arrays.

trigger_when:
  - User asks to minimize generation cost or compute optimal generator setpoints (dispatch).
  - Task requires co-optimizing energy with spinning reserves under capacity coupling.
  - Task mentions DC-OPF, economic dispatch, ED, or MATPOWER-style gencost data.
  - Building a cvxpy objective from a `gencost` array with `MODEL=2` polynomial costs.
  - Computing `operating_margin_MW` — uncommitted capacity beyond energy and reserves.
  - Formatting a `report.json` with `generator_dispatch`, `totals`, and `operating_margin_MW`.

do_not_use_when:
  - The task is purely about line flows, susceptance matrices, slack-bus selection, or thermal limits — use `dc-power-flow`.
  - Loading or parsing `network.json` / bus / branch arrays — use `power-flow-data` first, then this skill.
  - Unit commitment (binary on/off) or multi-period scheduling — this skill assumes a single-period continuous dispatch.

scope_and_approval: >
  Read-only on input arrays. Writes `report.json` (or the artifact named by the
  task) only when the task explicitly asks for it. Defaults to the CLARABEL solver;
  do not silently swap to OSQP, which is fragile for DC-OPF + reserves.

steps:
  - name: load-network-data
    description: >
      Delegate to `power-flow-data` to load `network.json`. Extract baseMVA and the
      numpy arrays buses, gens, branches, gencost. If the network includes operating
      reserves, also extract `reserve_capacity` (per-gen MW array) and
      `reserve_requirement` (system minimum MW float). Confirm `gencost[:,0] == 2`
      (polynomial cost model); piecewise-linear (MODEL=1) is out of scope here —
      see `references/cost-functions.md` for the format if encountered.
    outputs:
      - {name: baseMVA, type: float}
      - {name: buses, type: object, description: "MATPOWER bus array (n_bus x >=13)"}
      - {name: gens, type: object, description: "MATPOWER gen array (n_gen x >=10); col 0=GEN_BUS, col 8=PMAX, col 9=PMIN"}
      - {name: gencost, type: object, description: "MATPOWER gencost array; col 0=MODEL, col 3=NCOST, cols 4+=coeffs (highest order first)"}
      - {name: branches, type: object, description: "MATPOWER branch array (passed to dc-power-flow)"}
      - {name: reserve_capacity, type: "list[float]", nullable: true, description: "Per-gen reserve cap r_bar in MW"}
      - {name: reserve_requirement, type: float, nullable: true, description: "System reserve floor R in MW"}

  - name: declare-decision-variables
    description: >
      Declare `Pg = cp.Variable(n_gen)` in per-unit. When reserves are required,
      also declare `Rg = cp.Variable(n_gen)` in MW. The bus-angle variable `theta`
      is owned by `dc-power-flow` and shared by reference across both skills'
      constraint builders.
    depends_on: [load-network-data]
    outputs:
      - {name: Pg, type: object, description: "cvxpy.Variable(n_gen) in per-unit"}
      - {name: Rg, type: object, nullable: true, description: "cvxpy.Variable(n_gen) in MW; omit when no reserve requirement"}

  - name: build-cost-expression
    description: >
      Build the cvxpy total-cost expression. Handles variable NCOST per generator
      (3=quadratic c2*P^2+c1*P+c0, 2=linear c1*P+c0, 1=constant c0). Cost is
      evaluated in MW (Pg_MW = Pg * baseMVA) but Pg itself stays per-unit so it
      composes with the nodal balance from `dc-power-flow`.
    script: scripts/economic_dispatch.py
    depends_on: [declare-decision-variables]
    inputs:
      - {name: Pg, type: object}
      - {name: gencost, type: object}
      - {name: baseMVA, type: float}
    outputs:
      - {name: cost_expression, type: object, description: "cvxpy expression in $/hr"}

  - name: build-generator-limits
    description: >
      Add `Pmin/baseMVA <= Pg[i] <= Pmax/baseMVA` for every generator. Pmin is
      column 9 of `gens`; Pmax is column 8. Per-unit, to match the nodal balance.
    script: scripts/economic_dispatch.py
    depends_on: [declare-decision-variables]
    inputs:
      - {name: Pg, type: object}
      - {name: gens, type: object}
      - {name: baseMVA, type: float}
    outputs:
      - {name: gen_limit_constraints, type: "list[object]"}

  - name: build-reserve-coupling
    description: >
      Skip when `reserve_requirement` is absent. Otherwise add the MISO-style
      reserve constraints: `Rg >= 0`, `Rg[i] <= reserve_capacity[i]` (per-gen cap),
      `Pg_MW[i] + Rg[i] <= Pmax[i]` (capacity coupling — the cap that forces the
      energy/reserve trade-off), and `sum(Rg) >= reserve_requirement` (system floor).
      Rg lives in MW; remember to multiply Pg by baseMVA inside the coupling
      constraint.
    script: scripts/economic_dispatch.py
    depends_on: [declare-decision-variables]
    inputs:
      - {name: Pg, type: object}
      - {name: Rg, type: object}
      - {name: gens, type: object}
      - {name: baseMVA, type: float}
      - {name: reserve_capacity, type: "list[float]"}
      - {name: reserve_requirement, type: float}
    outputs:
      - {name: reserve_constraints, type: "list[object]"}

  - name: add-power-balance
    description: >
      Pick a balance form based on whether the network has transmission detail.
      With branches, defer to `dc-power-flow` for nodal balance (`Pg − Pd = B·θ`
      at each bus) + slack (`θ[slack] = 0`) + line thermal limits. Without
      transmission detail (single-bus / bulk case), add only the aggregate
      balance `cp.sum(Pg) == total_load_MW / baseMVA`. Most grid-dispatch tasks
      include branches and need the nodal form.
    depends_on: [declare-decision-variables]
    one_of:
      - "Nodal DC balance — delegate to dc-power-flow"
      - "Bulk single-bus balance: cp.sum(Pg) == total_load_pu"

  - name: solve
    description: >
      Construct `prob = cp.Problem(cp.Minimize(cost), constraints)` aggregating
      every constraint list (gen limits, reserves, nodal balance + slack + line
      limits from dc-power-flow). Call `prob.solve(solver=cp.CLARABEL)`. CLARABEL
      is the robust default for quadratic objectives with DC-OPF + reserve
      constraints; OSQP often fails on ill-conditioned cases. Assert
      `prob.status == "optimal"` before reading values.
    depends_on: [build-cost-expression, build-generator-limits, build-reserve-coupling, add-power-balance]
    outputs:
      - {name: solution_status, type: string}
      - {name: total_cost_dollars_per_hour, type: float}

  - name: format-dispatch-report
    description: >
      Build the `generator_dispatch` list (id, bus, output_MW, reserve_MW, pmax_MW),
      `totals` (cost_dollars_per_hour, load_MW, generation_MW, reserve_MW), and
      `operating_margin_MW = Σ (Pmax − output − reserve)`. Pass `Rg_value=None` if
      no reserves were modelled — reserves report as 0 and margin reduces to
      Σ (Pmax − output). The caller adds `most_loaded_lines` (top 3 by loading_pct
      descending) from `dc-power-flow` output before writing the final report.
    script: scripts/economic_dispatch.py
    depends_on: [solve]
    inputs:
      - {name: Pg_value, type: object, description: "Pg.value (per-unit numpy array)"}
      - {name: Rg_value, type: object, nullable: true, description: "Rg.value (MW numpy array) or None"}
      - {name: gens, type: object}
      - {name: buses, type: object}
      - {name: baseMVA, type: float}
      - {name: total_cost, type: float, description: "prob.value"}
    outputs:
      - {name: report, type: object, description: "dict with generator_dispatch, totals, operating_margin_MW (caller appends most_loaded_lines)"}

modes:
  - name: with-reserves
    body: >
      `reserve_capacity` and `reserve_requirement` present in `network.json`.
      Declare Rg, run `build-reserve-coupling`, include Rg.value in
      `format-dispatch-report`. This is the default for the
      grid-dispatch-operator task family.
  - name: energy-only
    body: >
      No reserve fields in `network.json`. Skip Rg, skip `build-reserve-coupling`,
      pass `Rg_value=None` to `format-dispatch-report` so reserves report as 0.

search_shortcuts:
  - category: Solver
    body: >
      CLARABEL (cvxpy >= 1.4) — interior-point, robust for DC-OPF + quadratic cost
      + reserves. Fallback: ECOS for purely linear costs. Avoid OSQP for this
      formulation.
  - category: MATPOWER column reference
    body: >
      gen: [GEN_BUS=0, ..., PG=1, QG=2, ..., PMAX=8, PMIN=9, ...].
      gencost (polynomial, MODEL=2): [MODEL=0, STARTUP=1, SHUTDOWN=2, NCOST=3,
      c_{n-1}..c_0 from index 4]. branch: [F_BUS=0, T_BUS=1, R=2, X=3, B=4,
      RATE_A=5, ...].
  - category: References
    body: >
      `references/cost-functions.md` — polynomial and piecewise-linear gencost
      formats with worked numeric examples. Load only when handling an
      unexpected gencost MODEL or debugging cost magnitudes.

integrations:
  - partner: dc-power-flow
    body: >
      Owns network-side modelling: susceptance matrix B, slack-bus selection,
      nodal balance `Pg − Pd = B·θ`, branch susceptances, line flow expressions,
      and thermal limit constraints. Compose by sharing the same cvxpy `theta`
      variable, appending its constraint list before solving, and reusing its
      branch-susceptance + bus-number-to-index dict when computing `most_loaded_lines`.
  - partner: power-flow-data
    body: >
      Owns loading and parsing of `network.json` — numpy arrays for buses, gens,
      branches, gencost, plus reserve fields. Provides the canonical bus-number-to-index
      dict used by both this skill and dc-power-flow.

scenarios:
  - need: >
      Grid dispatch operator task — DC power balance, generator and line limits,
      spinning reserve requirement with capacity coupling; emit `report.json`.
    context: >
      `network.json` includes `reserve_capacity` and a non-zero `reserve_requirement`,
      so reserves must be co-optimized.
    action: >
      1) power-flow-data → load arrays. 2) Declare Pg (pu), Rg (MW), theta (rad).
      3) This skill: cost via build_cost, gen limits via build_gen_limits, reserves
      via build_reserves. 4) dc-power-flow: B-matrix, nodal balance, slack, line
      limits. 5) cp.Problem(Minimize(cost), all_constraints).solve(CLARABEL).
      6) This skill's build_dispatch_report; append `most_loaded_lines` from
      dc-power-flow's line-flow loop (sorted descending by loading_pct, top 3);
      write report.json.
    outcome: >
      `report.json` with generator_dispatch, totals (cost/load/gen/reserve),
      most_loaded_lines, and operating_margin_MW.

  - need: Single-bus economic dispatch — no transmission detail, no reserves.
    action: >
      Skip dc-power-flow. Build cost + gen limits via this skill; add bulk balance
      `cp.sum(Pg) == total_load_MW / baseMVA`; solve with CLARABEL; format report
      with `Rg_value=None`.
    outcome: Per-generator output_MW and total cost.

  - need: Energy-only DC-OPF — network present, no reserve fields in network.json.
    action: >
      Run modes=`energy-only`: omit Rg entirely, skip build-reserve-coupling, pass
      `Rg_value=None` to build_dispatch_report.
    outcome: report.json with reserve_MW=0 across all generators and margin = Σ(Pmax − output).

anti_patterns:
  - Assuming gencost is always quadratic. NCOST varies per generator; branch on int(gencost[i,3]) for 3 (quad), 2 (linear), and 1 (constant). Hard-coding c2/c1/c0 indices crashes on linear-only rows.
  - Mixing per-unit and MW in a single expression. Pg is per-unit; cost coefficients are in MW; Rg is in MW. Convert at the boundary (Pg_MW = Pg * baseMVA) and document the unit of every variable.
  - Forgetting capacity coupling (Pg_MW + Rg <= Pmax). Without it, the optimizer can schedule reserves that exceed nameplate capacity and pass nothing else.
  - Mapping generator-to-bus via `bus_number - 1`. Bus numbers may be non-contiguous (e.g., case300). Use the bus-number-to-index dict from power-flow-data; gens[i,0] is the bus *number*, not the index.
  - Defaulting to OSQP for DC-OPF + reserves — it fails silently on ill-conditioned problems. Use CLARABEL and assert prob.status == "optimal".
  - Computing operating margin as Σ(Pmax − Pg) — uncommitted headroom must also exclude scheduled reserve, i.e. Σ(Pmax − Pg − Rg).
  - Reading prob.value before checking prob.status. A `status="infeasible"` or `"unbounded"` problem returns inf or None and silently corrupts the report.
  - Writing `most_loaded_lines` from the unsorted line-flow list. The task expects top 3 by loading_pct in descending order.
```
