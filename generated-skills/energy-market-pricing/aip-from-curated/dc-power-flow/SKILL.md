---
name: dc-power-flow
description: "DC power flow analysis for power systems. Use when computing power flows using DC approximation, building susceptance matrices, calculating line flows and loading percentages, or performing sensitivity analysis on transmission networks."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Compute DC power flow on a transmission network in MATPOWER format: build
  the susceptance matrix B from branch reactances, set the slack-bus angle
  reference, solve the linearized power balance Pg - Pd = B θ, and translate
  the angle solution into per-line MW flows and loading percentages. Provides
  the linear foundation for DC-OPF, congestion analysis, and contingency
  studies. Adds the bus-number→index mapping that prevents the classic
  off-by-one bug when bus IDs are non-contiguous (e.g., case300).

trigger_when:
  - Computing power flows using the DC approximation.
  - Building a B (susceptance) matrix from MATPOWER branch data.
  - Calculating line MW flows and loading percentages from bus angles.
  - Adding DC-OPF thermal-limit constraints to a CVXPY/Pyomo model.
  - Setting up a transmission contingency or line-rating sensitivity analysis.
  - User mentions DC power flow, B-matrix, susceptance, line flows, congestion, or thermal limits.

do_not_use_when:
  - "Full AC power flow with voltage magnitudes, reactive power, or losses is required (DC approximations break: lossless lines, |V|=1 pu, sin θ ≈ θ)."
  - The network is radial and a simple tree/shortest-path solver suffices.

scope_and_approval: >
  Read-only computation over the provided MATPOWER snapshot. No writes to
  the network file, no external calls. Safe to run without confirmation.

steps:
  - name: build-susceptance-matrix
    description: >
      Build the n_bus×n_bus susceptance matrix B and the per-branch
      susceptances b=1/x, plus the bus_num_to_idx mapping that resolves
      raw MATPOWER bus numbers to 0-indexed positions. Diagonals accumulate
      +b for every incident branch; off-diagonals carry -b symmetrically on
      (f, t) and (t, f). Branches with x == 0 contribute zero.
    script: scripts/build_b_matrix.py
    inputs:
      - name: branches
        type: list[object]
        description: MATPOWER branch matrix. Row layout used here -- col 0 from_bus, col 1 to_bus, col 3 x (reactance), col 5 RATE_A (MW).
      - name: buses
        type: list[object]
        description: MATPOWER bus matrix. Row layout used here -- col 0 bus number, col 1 bus type (3 = slack), col 2 Pd (MW load).
    outputs:
      - name: B
        type: object
        description: n_bus×n_bus susceptance matrix (np.ndarray).
      - name: branch_susceptances
        type: list[float]
        description: Per-branch b = 1/x, indexed in branch order; 0 where x == 0.
      - name: bus_num_to_idx
        type: object
        description: dict mapping int(bus_number) -> 0-indexed integer position.

  - name: set-slack-reference
    description: >
      Locate the slack bus (buses[i, 1] == 3) via find_slack_bus(buses) and
      add the angle-reference constraint theta[slack_idx] == 0 to the
      optimization model. Without this constraint the angle system is
      singular and has no unique solution.
    script: scripts/build_b_matrix.py
    depends_on: [build-susceptance-matrix]
    inputs:
      - name: buses
        type: list[object]
      - name: theta
        type: object
        description: CVXPY/Pyomo angle variable vector of length n_bus.
    outputs:
      - name: slack_idx
        type: integer
      - name: slack_constraint
        type: object
        description: The equality theta[slack_idx] == 0, appended to the constraint list.

  - name: add-power-balance
    description: |
      For each bus i append the per-unit nodal balance:
      Pg[i] - Pd[i] == B[i, :] @ theta.
      Pg[i] = sum of generator outputs at bus i, in pu (divide MW by baseMVA).
      Pd[i] = buses[i, 2] / baseMVA. Aggregate multiple generators at a bus
      before assembling Pg.
    depends_on: [build-susceptance-matrix]
    inputs:
      - name: B
        type: object
      - name: theta
        type: object
      - name: Pg
        type: object
        description: Per-bus generation expression vector (CVXPY/Pyomo or numeric) in pu.
      - name: Pd
        type: object
        description: Per-bus load vector in pu (buses[:, 2] / baseMVA).
      - name: baseMVA
        type: float
    outputs:
      - name: power_balance_constraints
        type: list[object]
        description: n_bus linear equality constraints (one per bus).

  - name: calculate-line-flows
    description: >
      Compute MW flow on every branch from solved bus angles using
      flow_MW = b * (theta[f] - theta[t]) * baseMVA, with f and t resolved
      through bus_num_to_idx and b drawn from branch_susceptances. Also
      reports loading_pct = |flow_MW| / RATE_A * 100, guarded against
      RATE_A == 0. Use after the optimization has been solved.
    script: scripts/build_b_matrix.py
    depends_on: [build-susceptance-matrix]
    inputs:
      - name: branches
        type: list[object]
      - name: branch_susceptances
        type: list[float]
      - name: theta
        type: object
        description: Solved bus angles (np.ndarray of radians, length n_bus).
      - name: baseMVA
        type: float
      - name: bus_num_to_idx
        type: object
    outputs:
      - name: line_flows
        type: list[object]
        description: One dict per branch with from, to, flow_MW, limit_MW, loading_pct.

  - name: add-thermal-limits
    description: |
      For each branch append the two linear inequalities:
        flow_MW <= RATE_A
        flow_MW >= -RATE_A
      where flow_MW = branch_susceptances[i] * (theta[f] - theta[t]) * baseMVA
      and (f, t) are resolved via bus_num_to_idx. Skip branches with
      RATE_A == 0 (unconstrained). This is the line-rating constraint block
      for DC-OPF.
    depends_on: [build-susceptance-matrix]
    inputs:
      - name: branches
        type: list[object]
      - name: branch_susceptances
        type: list[float]
      - name: theta
        type: object
      - name: baseMVA
        type: float
      - name: bus_num_to_idx
        type: object
    outputs:
      - name: thermal_limit_constraints
        type: list[object]
        description: Up to 2 * n_branch linear inequalities.

anti_patterns:
  - Using `br[0] - 1` (or `int(br[0]) - 1`) as a branch endpoint index. Bus numbers may be non-contiguous (case300); always resolve through `bus_num_to_idx`.
  - Treating B as asymmetric. B is symmetric — every off-diagonal update must touch both B[f, t] and B[t, f].
  - Omitting the slack constraint theta[slack] == 0. Without it the angle system is singular and the model has no unique solution.
  - Mixing MW and per-unit in the power balance. Pg and Pd must both be in pu (divide by baseMVA) when paired with B θ.
  - Reporting `b * (theta[f] - theta[t])` as MW. Multiply by baseMVA to convert per-unit flow to MW.
  - Dividing by zero on branches with x == 0 or RATE_A == 0. Guard susceptance with `if x != 0` and loading with `if limit_MW > 0`.

scenarios:
  - need: Solve DC power flow on a MATPOWER case where bus IDs are non-contiguous (e.g., case300).
    context: network.json holds bus, branch, and gen matrices; bus numbers jump (1, 2, 5, 7, ...).
    action: Call `build_susceptance_matrix(branches, buses)` for B and `bus_num_to_idx`; call `find_slack_bus(buses)`; assemble Pg - Pd == B θ with theta[slack_idx] == 0; solve; then `calculate_line_flows(...)` for per-line MW and loading.
    outcome: Bus angles and per-line MW flows free of the off-by-one bus-indexing bug.
  - need: Add thermal-limit constraints to a DC-OPF model.
    context: B and branch_susceptances already constructed; theta is a CVXPY variable of length n_bus.
    action: For each branch, append `b * (theta[f] - theta[t]) * baseMVA <= RATE_A` and `>= -RATE_A` to the model's constraint list, using bus_num_to_idx to resolve f and t. Skip branches where RATE_A == 0.
    outcome: Linear thermal limits ready to compose with the DC-OPF objective and other constraints.
  - need: Identify binding (congested) transmission lines after solving DC-OPF.
    context: theta values are populated post-solve; the report needs lines at >= 99% loading.
    action: Run `calculate_line_flows(...)`, then filter `line_flows` for `loading_pct >= 99`.
    outcome: A list of binding branches with from, to, flow_MW, and limit_MW for the congestion section of the report.
```
