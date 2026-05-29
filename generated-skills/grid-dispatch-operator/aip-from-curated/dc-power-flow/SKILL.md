---
name: dc-power-flow
description: "DC power flow analysis for power systems. Use when computing power flows using DC approximation, building susceptance matrices, calculating line flows and loading percentages, formulating DC-OPF nodal balance and thermal-limit constraints, or performing sensitivity analysis on transmission networks."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  DC power flow modeling primitives for transmission networks in MATPOWER format.
  Provides the building blocks for assembling a DC optimal power flow (DC-OPF)
  problem and for analyzing post-solve flows: bus-number → 0-indexed mapping,
  susceptance matrix B construction from branch reactances, slack-bus reference
  pinning, nodal power balance constraints, line thermal limits, and per-branch
  MW flow and loading-percentage computation. Uses the DC approximation —
  lossless lines (R ≈ 0), flat voltage (|V| = 1 pu), and small angles
  (sin θ ≈ θ, cos θ ≈ 1) — so flows depend only on bus angles θ and line
  reactances X.

trigger_when:
  - Computing power flows using the DC approximation on a transmission network.
  - Building a susceptance (B) matrix from MATPOWER branch reactances.
  - Calculating per-line MW flow, MW limit, and loading percentage from solved bus angles.
  - Formulating DC-OPF constraints — nodal balance, slack-angle reference, thermal limits.
  - Reporting the most heavily loaded transmission lines after a dispatch solve.
  - Performing sensitivity analysis on a transmission network.
  - Working with cases where bus numbers are non-contiguous (e.g., case300).

do_not_use_when:
  - AC power flow is required (voltage magnitudes, reactive power, or losses matter).

steps:
  - name: load-network-arrays
    description: >
      Parse network.json (MATPOWER) and convert the bus and branch lists to numpy
      2-D arrays; capture baseMVA for per-unit conversion. See the power-flow-data
      skill for a full loader. Minimum needed for this skill: buses, branches, baseMVA.
    outputs:
      - name: buses
        type: object
        description: numpy 2-D array of MATPOWER bus rows (column 0 is bus number, column 1 is bus type, column 2 is Pd in MW).
      - name: branches
        type: object
        description: numpy 2-D array of MATPOWER branch rows (cols 0/1 are from/to bus number, col 3 is reactance X, col 5 is RATE_A in MW).
      - name: baseMVA
        type: float
        description: System MVA base used for pu ↔ MW conversion.

  - name: build-susceptance-matrix
    description: >
      Build the n_bus × n_bus susceptance matrix B and a per-branch susceptance
      list, returning the bus_number → 0-indexed mapping that every downstream
      step requires. Backed by build_susceptance_matrix in
      scripts/build_b_matrix.py. Bus numbers may be non-contiguous — always go
      through bus_num_to_idx, never use `bus_number - 1` as an array index.
      Branches with reactance x == 0 contribute b = 0 (skipped, not 1/0).
    script: scripts/build_b_matrix.py
    inputs:
      - name: branches
        type: object
      - name: buses
        type: object
    outputs:
      - name: B
        type: object
        description: n_bus × n_bus numpy susceptance matrix. Diagonal entries are the sum of incident branch susceptances; off-diagonals are −b for each connecting branch.
      - name: branch_susceptances
        type: list[float]
        description: b = 1/x for each branch (0 if x == 0), in branch-array order.
      - name: bus_num_to_idx
        type: object
        description: dict mapping MATPOWER bus number → 0-indexed array position.

  - name: identify-slack-bus
    description: >
      Find the slack bus — the row where the type column equals 3 — and pin its
      angle to zero so the DC-OPF is well-posed (otherwise the angle vector is
      determined only up to a constant and the problem is rank-deficient).
      There is exactly one slack bus per MATPOWER case. Inline snippet:
      ```python
      slack_idx = next(i for i in range(n_bus) if buses[i, 1] == 3)
      constraints.append(theta[slack_idx] == 0)
      ```
    inputs:
      - name: buses
        type: object
    outputs:
      - name: slack_idx
        type: integer
      - name: slack_constraint
        type: object
        description: cvxpy constraint `theta[slack_idx] == 0` appended to the constraint list.

  - name: formulate-nodal-power-balance
    description: >
      For every bus i, enforce `Pg_i − Pd_i == B[i, :] @ theta` in per-unit.
      Map each generator to its bus via bus_num_to_idx; take loads from
      `buses[i, 2]` (MW) and divide by baseMVA. Use a single cvxpy Variable
      `theta` of length n_bus. Example:
      ```python
      theta = cp.Variable(n_bus)
      for i in range(n_bus):
          Pd_pu = buses[i, 2] / baseMVA
          Pg_at_bus = sum(Pg[g] for g in range(n_gen)
                          if bus_num_to_idx[int(gens[g, 0])] == i)
          constraints.append(Pg_at_bus - Pd_pu == B[i, :] @ theta)
      ```
      Pg here is the per-unit generator-output Variable defined by the
      economic-dispatch skill; this step contributes only the nodal balance rows.
    inputs:
      - name: B
        type: object
      - name: buses
        type: object
      - name: bus_num_to_idx
        type: object
      - name: baseMVA
        type: float
      - name: Pg
        type: object
        description: cvxpy Variable of per-unit generator outputs (from economic-dispatch).
    outputs:
      - name: theta
        type: object
        description: cvxpy Variable of bus angles (radians), length n_bus.
      - name: nodal_balance_constraints
        type: object
        description: n_bus cvxpy equality constraints appended to the constraint list.

  - name: formulate-line-limits
    description: >
      For every branch enforce the thermal limit as two linear inequalities
      `−rate ≤ flow_MW ≤ rate`, where
      `flow_MW = b * (theta[f] − theta[t]) * baseMVA` with b taken from
      branch_susceptances and f, t from bus_num_to_idx. Skip branches with
      RATE_A == 0 (no enforced limit). Example:
      ```python
      for idx, br in enumerate(branches):
          f = bus_num_to_idx[int(br[0])]
          t = bus_num_to_idx[int(br[1])]
          b = branch_susceptances[idx]
          rate = br[5]
          if rate > 0:
              flow = b * (theta[f] - theta[t]) * baseMVA
              constraints.append(flow <= rate)
              constraints.append(flow >= -rate)
      ```
    inputs:
      - name: theta
        type: object
      - name: branches
        type: object
      - name: branch_susceptances
        type: list[float]
      - name: bus_num_to_idx
        type: object
      - name: baseMVA
        type: float
    outputs:
      - name: line_limit_constraints
        type: object
        description: cvxpy inequality constraints appended to the constraint list.

  - name: compute-line-flows
    description: >
      After `problem.solve()`, compute flow_MW, limit_MW, and loading_pct for
      every branch. Backed by calculate_line_flows in scripts/build_b_matrix.py.
      Returns one dict per branch with from-bus, to-bus, flow_MW, limit_MW,
      loading_pct. To report the most heavily loaded lines, sort by loading_pct
      descending and slice (e.g. `sorted(..., key=lambda r: r['loading_pct'],
      reverse=True)[:3]`). Pass `theta.value` (not the Variable) as
      `theta_solved`.
    script: scripts/build_b_matrix.py
    inputs:
      - name: branches
        type: object
      - name: branch_susceptances
        type: list[float]
      - name: theta_solved
        type: object
        description: theta.value (numpy array) returned by cvxpy after problem.solve().
      - name: baseMVA
        type: float
      - name: bus_num_to_idx
        type: object
    outputs:
      - name: line_flows
        type: list[object]
        description: List of {from, to, flow_MW, limit_MW, loading_pct} per branch.

scenarios:
  - need: Assemble B and identify the slack for an IEEE 14-bus case.
    action: Call `build_susceptance_matrix(branches, buses)` → B, branch_susceptances, bus_num_to_idx. Find type==3 row to get slack_idx.
    outcome: B (14×14), branch_susceptances (20-length), bus_num_to_idx, slack_idx, all ready for DC-OPF constraint formulation.
  - need: Report the top three most heavily loaded transmission lines after a DC-OPF solve.
    context: theta solved by cvxpy DC-OPF; branch rates from RATE_A (col 5).
    action: >
      Call calculate_line_flows(branches, branch_susceptances, theta.value, baseMVA,
      bus_num_to_idx), then sort the returned rows by loading_pct descending and take
      the first three.
    outcome: Three {from, to, loading_pct} entries ready to embed in report.json under most_loaded_lines.
  - need: Handle a case (e.g., case300) where bus numbers are non-contiguous.
    action: Always index via bus_num_to_idx returned by build_susceptance_matrix; never use `int(br[0]) - 1`.
    outcome: B, flows, and constraints index correctly without IndexError or silently wrong rows.

anti_patterns:
  - Using `bus_number - 1` to index `buses`, `branches`, or `theta`. Bus numbers may be non-contiguous (e.g., case300). Always route through bus_num_to_idx.
  - Forgetting to pin the slack-bus angle (`theta[slack_idx] == 0`). Without it, the DC-OPF is rank-deficient and theta is determined only up to a constant.
  - Mixing per-unit and MW. theta and Pg are pu (radians and pu-MW); RATE_A, Pd column, and report fields are MW. Convert at the boundary via baseMVA.
  - Dividing by zero reactance. Treat x == 0 branches as b = 0 (skip from B assembly and from flow-limit constraints) instead of 1/0.
  - Adding `|flow| <= rate` as a single non-linear constraint. Use the two linear inequalities `-rate <= flow <= rate` so the problem stays an LP/QP.
  - Passing the cvxpy Variable `theta` into `calculate_line_flows` instead of `theta.value`. The script expects a numpy array of solved angles.
  - Building B by iterating over buses instead of branches. B is assembled per-branch (each branch contributes +b to two diagonals and -b to two off-diagonals).
```
