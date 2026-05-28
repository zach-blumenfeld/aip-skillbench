---
name: economic-dispatch
description: "Generator economic dispatch and cost optimization for power systems. Use when minimizing generation costs, computing optimal generator setpoints, calculating operating margins, or working with generator cost functions."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Generator economic dispatch and cost optimization for power systems.
  Minimize total generation cost while meeting load demand and respecting
  generator limits. Covers MATPOWER data indexing, polynomial cost
  functions, CVXPY formulation, power balance, optional reserve
  co-optimization, operating-margin computation, and dispatch output
  formatting.

trigger_when:
  - Minimizing total generation cost across multiple generators.
  - Computing optimal generator setpoints (Pg) for a given load.
  - Calculating operating margin or remaining capacity headroom.
  - Working with MATPOWER-format generator cost functions (gencost).
  - Co-optimizing energy and operating reserves.
  - User mentions economic dispatch, OPF energy schedule, generator dispatch, or reserve co-optimization.

do_not_use_when:
  - Network/line limits drive the problem and a full DC-OPF nodal balance is required — defer to the dc-power-flow skill for the balance constraint (this skill still handles cost objective, generator limits, and reserves).
  - Unit-commitment-style binary on/off decisions are needed; this skill only handles continuous dispatch.

steps:
  - name: parse-generator-data
    description: |
      Read MATPOWER generator-array columns by index (0-indexed):
        index 0 → GEN_BUS (bus number, 1-indexed in the data)
        index 8 → PMAX (max real power, MW)
        index 9 → PMIN (min real power, MW)

      Build a bus-number → array-index mapping so non-contiguous bus
      numbers work:

        bus_num_to_idx = {int(buses[i, 0]): i for i in range(n_bus)}
        gen_bus = [bus_num_to_idx[int(g[0])] for g in gens]
        pmax_MW = gen[8]
        pmin_MW = gen[9]

  - name: parse-cost-functions
    description: |
      MATPOWER gencost array (polynomial, MODEL=2):
        index 0 → MODEL (2 = polynomial)
        index 1 → STARTUP cost ($)
        index 2 → SHUTDOWN cost ($)
        index 3 → NCOST (number of coefficients)
        index 4+ → coefficients, highest order first

      Quadratic (NCOST=3): [c2, c1, c0] at indices 4, 5, 6.
      Linear     (NCOST=2): [c1, c0]     at indices 4, 5.

      Cost = c₂·P² + c₁·P + c₀ ($/hr) with P in MW.

      For piecewise-linear costs (MODEL=1), marginal-cost derivation, and
      typical coefficient ranges by generator technology, see
      references/cost-functions.md.

  - name: build-objective
    description: |
      Declare per-unit decision variables in CVXPY and convert to MW only
      inside the cost expression so variable NCOST is handled cleanly:

        import cvxpy as cp

        Pg = cp.Variable(n_gen)  # per-unit
        cost = 0
        for i in range(n_gen):
            ncost = int(gencost[i, 3])
            Pg_MW = Pg[i] * baseMVA

            if ncost >= 3:
                c2, c1, c0 = gencost[i, 4], gencost[i, 5], gencost[i, 6]
                cost += c2 * cp.square(Pg_MW) + c1 * Pg_MW + c0
            elif ncost == 2:
                c1, c0 = gencost[i, 4], gencost[i, 5]
                cost += c1 * Pg_MW + c0
            else:
                cost += gencost[i, 4] if ncost >= 1 else 0

  - name: add-generator-limits
    description: |
      Enforce PMIN ≤ Pg ≤ PMAX. Convert MW limits to per-unit when
      comparing against Pg (which is per-unit):

        constraints = []
        for i in range(n_gen):
            pmin = gens[i, 9] / baseMVA
            pmax = gens[i, 8] / baseMVA
            constraints.append(Pg[i] >= pmin)
            constraints.append(Pg[i] <= pmax)

  - name: add-power-balance
    description: |
      Total generation must equal total load. For a single-bus / copperplate
      model:

        total_load_pu = sum(buses[i, 2] for i in range(n_bus)) / baseMVA
        constraints.append(cp.sum(Pg) == total_load_pu)

      For DC-OPF with network/line constraints, replace this lumped
      constraint with the per-bus nodal balance from the dc-power-flow
      skill.

  - name: add-reserve-cooptimization
    description: |
      When operating reserves are required (data['reserve_requirement']
      present), add reserve decision variables, per-generator capacity
      caps, capacity coupling between energy and reserves, and a
      system-wide reserve floor:

        reserve_capacity   = np.array(data['reserve_capacity'])  # MW per generator
        reserve_requirement = data['reserve_requirement']         # MW system-wide

        Rg = cp.Variable(n_gen)  # reserves, in MW
        constraints.append(Rg >= 0)

        for i in range(n_gen):
            constraints.append(Rg[i] <= reserve_capacity[i])     # cap
            pmax_MW = gens[i, 8]
            Pg_MW = Pg[i] * baseMVA
            constraints.append(Pg_MW + Rg[i] <= pmax_MW)         # coupling

        constraints.append(cp.sum(Rg) >= reserve_requirement)    # system floor

      Skip this step entirely when no reserve data is provided.

  - name: solve
    description: |
      Build and solve the problem. For quadratic costs (especially combined
      with network constraints) use CLARABEL — a robust interior-point
      solver:

        prob = cp.Problem(cp.Minimize(cost), constraints)
        prob.solve(solver=cp.CLARABEL)

  - name: compute-operating-margin
    description: |
      Operating margin is the "uncommitted" headroom — capacity available
      beyond scheduled generation AND reserves:

        Pg_MW = Pg.value * baseMVA
        Rg_MW = Rg.value  # already MW
        operating_margin_MW = sum(
            gens[i, 8] - Pg_MW[i] - Rg_MW[i] for i in range(n_gen)
        )

  - name: format-dispatch-output
    description: |
      Build a per-generator dispatch list with 1-indexed ids, rounded to
      two decimals:

        generator_dispatch = []
        for i in range(n_gen):
            generator_dispatch.append({
                "id": i + 1,
                "bus": int(gens[i, 0]),
                "output_MW":  round(float(Pg_MW[i]), 2),
                "reserve_MW": round(float(Rg_MW[i]), 2),
                "pmax_MW":    round(float(gens[i, 8]), 2),
            })

  - name: compute-totals
    description: |
      Aggregate cost and MW totals for the dispatch summary:

        total_gen_MW     = sum(Pg_MW)
        total_load_MW    = sum(buses[i, 2] for i in range(n_bus))
        total_reserve_MW = sum(Rg_MW)

        totals = {
            "cost_dollars_per_hour": round(float(prob.value), 2),
            "load_MW":       round(float(total_load_MW), 2),
            "generation_MW": round(float(total_gen_MW), 2),
            "reserve_MW":    round(float(total_reserve_MW), 2),
        }

decisions:
  - signal: gencost row has NCOST = 3.
    action: Use quadratic form c₂·P² + c₁·P + c₀ with coefficients at indices 4, 5, 6.
  - signal: gencost row has NCOST = 2.
    action: Use linear form c₁·P + c₀ with coefficients at indices 4, 5.
  - signal: gencost row has NCOST ≤ 1.
    action: Treat as constant cost (gencost[i, 4] when NCOST ≥ 1, otherwise 0).
  - signal: Network/line limits drive the problem (DC-OPF) rather than a copperplate balance.
    action: Replace the lumped sum(Pg) == total_load constraint with the per-bus nodal balance from the dc-power-flow skill; keep the cost objective, generator limits, and reserve handling from this skill.
  - signal: OSQP fails or returns inaccurate values on an ill-conditioned quadratic problem.
    action: Re-solve with CLARABEL — it is more robust for DC-OPF with reserves.
  - signal: data['reserve_requirement'] is absent from the input.
    action: Skip add-reserve-cooptimization; do not create Rg; treat reserve_MW as 0 in outputs.
  - signal: Bus numbers in the network are non-contiguous or do not start at 0.
    action: Index generators through bus_num_to_idx instead of using the raw bus number as an array index.

anti_patterns:
  - Assuming bus numbers are contiguous or 0-indexed — always build a bus_num_to_idx mapping from buses[:, 0].
  - Hardcoding NCOST = 3 instead of branching on gencost[i, 3]; linear and constant cost rows will silently misprice.
  - Mixing per-unit and MW units in the same expression — keep Pg in per-unit and convert to MW only inside the cost objective and reserve coupling.
  - Defaulting to OSQP for DC-OPF with reserves; it is fragile on ill-conditioned problems, prefer CLARABEL.
  - Omitting the capacity-coupling constraint Pg_MW + Rg ≤ Pmax when reserves are added — reserves would otherwise overlap committed energy.
  - Computing operating margin without subtracting reserves — margin is headroom beyond BOTH energy and reserves, not just energy.
```
