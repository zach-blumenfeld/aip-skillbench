---
name: locational-marginal-prices
description: "Extract locational marginal prices (LMPs) from DC-OPF solutions using dual values. Use when computing nodal electricity prices, reserve clearing prices, or performing price impact analysis."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Extract Locational Marginal Prices (LMPs) — the marginal cost of serving one
  additional MW of load at each bus — from a CVXPY DC-OPF solution by reading
  the dual values (shadow prices) of the nodal power balance constraints. The
  same dual-extraction pattern generalises to reserve clearing prices, binding
  transmission lines, and counterfactual price-impact studies.

trigger_when:
  - Computing nodal electricity prices ($/MWh) from a DC-OPF solution.
  - Extracting the reserve market clearing price (MCP) from a system reserve requirement.
  - Identifying binding transmission lines and congestion-driven LMP separation.
  - Running counterfactual analysis (e.g., relaxing a thermal limit) to quantify the shadow price of a constraint.
  - User mentions LMPs, nodal prices, shadow prices, congestion pricing, or price impact analysis.

steps:
  - name: store-balance-constraint-refs
    description: |
      Before solving, build each nodal power-balance constraint as a Python
      object and keep a reference to it in a list. CVXPY only exposes
      `.dual_value` on constraint objects you hold a reference to — appending
      anonymously into the master `constraints` list is not enough.

      ```python
      import cvxpy as cp

      balance_constraints = []

      for i in range(n_bus):
          pg_at_bus = sum(Pg[g] for g in range(n_gen) if gen_bus[g] == i)
          pd = buses[i, 2] / baseMVA

          balance_con = pg_at_bus - pd == B[i, :] @ theta
          balance_constraints.append(balance_con)
          constraints.append(balance_con)
      ```
  - name: solve-dc-opf
    description: |
      Solve the problem with a solver that returns dual values for the
      constraint class in use. CLARABEL works for the linear/quadratic DC-OPF.

      ```python
      prob = cp.Problem(cp.Minimize(cost), constraints)
      prob.solve(solver=cp.CLARABEL)
      ```
  - name: read-dual-values
    description: |
      After solve, iterate the stored balance constraints and read each
      `.dual_value`. Guard against `None` (which indicates the solver did not
      return a dual for that constraint).
  - name: scale-to-dollars-per-mwh
    description: |
      Balance constraints are written in per-unit, so the raw dual is in
      $/per-unit-MW. Multiply by `baseMVA` to get $/MWh. Emit one record per
      bus.

      ```python
      lmp_by_bus = []
      for i in range(n_bus):
          bus_num = int(buses[i, 0])
          dual_val = balance_constraints[i].dual_value
          lmp = float(dual_val) * baseMVA if dual_val is not None else 0.0
          lmp_by_bus.append({
              "bus": bus_num,
              "lmp_dollars_per_MWh": round(lmp, 2),
          })
      ```

decisions:
  - signal: LMP at a bus is positive (typical case).
    action: >
      Interpret as: increasing load at that bus increases total system cost.
      No special handling required.
  - signal: LMP at a bus is negative.
    action: >
      Treat as physically valid, not an error. Negative LMPs occur when cheap
      generation is trapped behind a congested line and adding load locally
      relieves congestion by consuming excess generation. Magnitudes of
      thousands of $/MWh are normal in heavily congested networks.
  - signal: A balance constraint's `dual_value` is `None` after solve.
    action: >
      Confirm the constraint was added to the master `constraints` list before
      `prob.solve()` and that the solver in use returns duals (CLARABEL does).
      Substitute `0.0` only as a defensive default, not as a silent fallback
      for a misconfigured solve.

scenarios:
  - need: Extract the system reserve clearing price (reserve MCP).
    context: >
      The reserve MCP is the dual of the system-wide reserve requirement
      constraint — same pattern as a nodal LMP, just a single scalar.
    action: |
      Keep a reference to the reserve constraint before adding it to the
      problem; read its dual after solving.

      ```python
      reserve_con = cp.sum(Rg) >= reserve_requirement
      constraints.append(reserve_con)

      # After solving:
      reserve_mcp = float(reserve_con.dual_value) if reserve_con.dual_value is not None else 0.0
      ```
    outcome: >
      A single $/MW value representing the marginal cost of one additional MW
      of system-wide reserve capacity.
  - need: Identify binding transmission lines driving LMP separation.
    context: >
      Lines at or near thermal limits cause congestion and price separation
      between buses. Line flow calculation details live in the `dc-power-flow`
      skill.
    action: |
      After solve, compute per-branch loading as a percentage of the rated
      limit and flag lines at or above the binding threshold (default 99%).

      ```python
      BINDING_THRESHOLD = 99.0  # Percent loading

      binding_lines = []
      for k, br in enumerate(branches):
          f = bus_num_to_idx[int(br[0])]
          t = bus_num_to_idx[int(br[1])]
          x, rate = br[3], br[5]

          if x != 0 and rate > 0:
              b = 1.0 / x
              flow_MW = b * (theta.value[f] - theta.value[t]) * baseMVA
              loading_pct = abs(flow_MW) / rate * 100

              if loading_pct >= BINDING_THRESHOLD:
                  binding_lines.append({
                      "from": int(br[0]),
                      "to": int(br[1]),
                      "flow_MW": round(float(flow_MW), 2),
                      "limit_MW": round(float(rate), 2),
                  })
      ```
    outcome: >
      A list of binding branches that explain LMP separation patterns observed
      in the nodal price vector.
  - need: Counterfactual analysis — quantify the impact of relaxing a transmission constraint.
    context: >
      Used to estimate the value of upgrading or de-rating a specific line.
      The shadow price of a binding constraint equals the per-unit cost
      reduction obtained by relaxing it.
    action: |
      Solve the base case (record cost, LMPs, binding lines), modify the
      target branch's thermal limit, re-solve, and compare.

      ```python
      # Modify line limit (e.g., increase by 20%)
      for k in range(n_branch):
          br_from, br_to = int(branches[k, 0]), int(branches[k, 1])
          if (br_from == target_from and br_to == target_to) or \
             (br_from == target_to and br_to == target_from):
              branches[k, 5] *= 1.20  # 20% increase
              break

      # After solving both cases:
      cost_reduction = base_cost - cf_cost  # Should be >= 0

      # LMP changes per bus
      for bus_num in base_lmp_map:
          delta = cf_lmp_map[bus_num] - base_lmp_map[bus_num]
          # Negative delta = price decreased (congestion relieved)

      # Congestion relieved if line was binding in base but not in counterfactual
      congestion_relieved = was_binding_in_base and not is_binding_in_cf
      ```
    outcome: >
      Economic intuition: relaxing a binding constraint cannot increase cost
      (it decreases or stays the same); the cost reduction quantifies the
      constraint's shadow price; and LMP convergence after relieving
      congestion indicates reduced price separation across the network.

anti_patterns:
  - Adding balance constraints to the `constraints` list without keeping a separate Python reference — `.dual_value` is unreachable without the reference.
  - Choosing a solver that does not expose dual values for the constraint class in use; verify the solver returns duals before debugging missing LMPs.
  - Forgetting to multiply the raw dual by `baseMVA` — the constraint is in per-unit, the output must be $/MWh.
  - Treating negative LMPs as a numerical error and clamping them to zero; they are physically valid and diagnostic of congestion patterns.
  - Computing line loading without guarding against zero reactance (`x == 0`) or zero rated capacity (`rate <= 0`).
```
