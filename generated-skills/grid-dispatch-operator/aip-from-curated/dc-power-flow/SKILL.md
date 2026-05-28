---
name: dc-power-flow
description: "DC power flow analysis for power systems. Use when computing power flows using the DC approximation, building susceptance matrices, calculating line flows and loading percentages, enforcing thermal limits, or performing sensitivity analysis on transmission networks in MATPOWER-style data."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Compute DC power flow on a transmission network in MATPOWER format.
  DC power flow is the linearized approximation of AC power flow (lossless
  lines R ≈ 0, flat voltage V = 1.0 pu, small-angle sin θ ≈ θ) so power
  flow depends only on bus angles θ and line reactances X. Used as the
  network model inside economic dispatch, OPF, and contingency analysis.

trigger_when:
  - Solving DC optimal power flow or economic dispatch on a MATPOWER snapshot.
  - Building a susceptance matrix B from branch reactances.
  - Computing line flows, line loading percentages, or ranking most-loaded lines.
  - Enforcing transmission thermal limits (RATE_A) as linear constraints in an LP/QP.
  - Doing sensitivity analysis (PTDF-like) on a transmission network.
  - Reading the network from a `network.json` with `bus` / `branch` / `gen` / `baseMVA` keys.

do_not_use_when:
  - The task explicitly requires AC power flow, voltage magnitude solutions, or reactive power — DC drops all of those.
  - Losses materially matter for the answer (e.g., loss-allocation studies).

steps:
  - name: load-network
    description: >
      Load the MATPOWER-format network. Expect `baseMVA` (float), `bus`
      (rows: [bus_i, type, Pd, Qd, ...]), `branch` (rows: [from, to, r, x, b,
      rateA, ...]), `gen` (rows: [gen_bus, Pg, Qg, ..., Pmax, Pmin, ...]).
      Pd is in MW; convert to per-unit with `Pd / baseMVA` when assembling
      the power-balance vector.
    outputs:
      - name: buses
        type: object
        description: "n_bus × ncols numpy array of bus data."
      - name: branches
        type: object
        description: "n_branch × ncols numpy array of branch data."
      - name: gens
        type: object
        description: "n_gen × ncols numpy array of generator data."
      - name: baseMVA
        type: float

  - name: build-bus-index
    description: >
      Build `bus_num_to_idx = {int(buses[i, 0]): i for i in range(n_bus)}`.
      Power-system bus numbers may not be contiguous (e.g., MATPOWER
      case300 has non-sequential IDs); always map bus number → 0-indexed
      position. NEVER assume `idx = bus_number - 1`.
    inputs:
      - name: buses
        type: object
    outputs:
      - name: bus_num_to_idx
        type: object
        description: "dict[int, int] from raw bus number to 0-indexed row."

  - name: build-b-matrix
    description: >
      Build the n_bus × n_bus susceptance matrix B from branch reactances
      using the bus index. For each branch (f, t, x) with x ≠ 0, b = 1/x,
      then B[f,f] += b; B[t,t] += b; B[f,t] -= b; B[t,f] -= b. Branches
      with x == 0 are skipped and recorded with susceptance 0. Returns
      `branch_susceptances` aligned by branch row so downstream steps can
      reuse it.
    script: scripts/build_b_matrix.py
    inputs:
      - name: branches
        type: object
      - name: buses
        type: object
    outputs:
      - name: B
        type: object
        description: "n_bus × n_bus numpy susceptance matrix; symmetric."
      - name: branch_susceptances
        type: list[float]
        description: "Per-branch susceptance b = 1/x (0 where x == 0), aligned with branches rows."
      - name: bus_num_to_idx
        type: object

  - name: set-up-angle-constraints
    description: >
      Declare angle variables `theta` of length n_bus. Find the slack bus
      (the row where `buses[i, 1] == 3`) and constrain its angle to zero
      as the reference:
        slack_idx = next(i for i in range(n_bus) if buses[i, 1] == 3)
        constraints.append(theta[slack_idx] == 0)
      Exactly one slack bus is expected in well-formed MATPOWER cases.
    inputs:
      - name: buses
        type: object
    outputs:
      - name: theta
        type: object
        description: "Vector of n_bus angle variables (radians)."
      - name: slack_idx
        type: integer
      - name: angle_constraints
        type: list[object]
        description: "List containing the slack reference constraint (and any other angle constraints added here)."

  - name: set-up-power-balance
    description: >
      Enforce DC power balance at every bus: `Pg_i - Pd_i == (B @ theta)_i`
      in per-unit. Build `Pg_pu` from generator decision variables grouped
      by their bus index (sum of generators at the same bus), and `Pd_pu`
      from `buses[:, 2] / baseMVA`. Append one equality constraint per bus
      (or a single vector equality `Pg_pu - Pd_pu == B @ theta`).
    inputs:
      - name: buses
        type: object
      - name: gens
        type: object
      - name: B
        type: object
      - name: theta
        type: object
      - name: baseMVA
        type: float
      - name: bus_num_to_idx
        type: object
    outputs:
      - name: power_balance_constraints
        type: list[object]

  - name: enforce-thermal-limits
    description: >
      For each branch, enforce |flow| ≤ RATE_A as two linear constraints:
        f = bus_num_to_idx[int(br[0])]; t = bus_num_to_idx[int(br[1])]
        b = branch_susceptances[idx]
        rate = br[5]  # RATE_A column
        flow = b * (theta[f] - theta[t]) * baseMVA
        constraints.append(flow <= rate)
        constraints.append(flow >= -rate)
      Skip branches with rate ≤ 0 (treat as unlimited) unless the task
      states otherwise.
    inputs:
      - name: branches
        type: object
      - name: branch_susceptances
        type: list[float]
      - name: theta
        type: object
      - name: baseMVA
        type: float
      - name: bus_num_to_idx
        type: object
    outputs:
      - name: thermal_constraints
        type: list[object]

  - name: solve
    description: >
      Hand the assembled angle variables, generator variables, equality
      and inequality constraints, and the objective (defined by the
      calling skill, e.g. economic-dispatch) to a convex LP/QP solver
      (CVXPY with ECOS/OSQP/CLARABEL is the common choice). After
      solve, read out numeric angles `theta.value` for downstream line-flow
      computation.
    depends_on: [set-up-angle-constraints, set-up-power-balance, enforce-thermal-limits]
    outputs:
      - name: theta_value
        type: list[float]
        description: "Solved bus angles in radians, length n_bus."

  - name: compute-line-flows
    description: >
      Compute per-branch flow in MW from solved angles using
      `calculate_line_flows(branches, branch_susceptances, theta_value,
      baseMVA, bus_num_to_idx)` in `scripts/build_b_matrix.py`. Each row
      yields `{from, to, flow_MW, limit_MW, loading_pct}` where
      `flow_MW = b * (theta[f] - theta[t]) * baseMVA` and
      `loading_pct = abs(flow_MW) / limit_MW * 100` when `limit_MW > 0`,
      else 0.
    script: scripts/build_b_matrix.py
    depends_on: [solve]
    inputs:
      - name: branches
        type: object
      - name: branch_susceptances
        type: list[float]
      - name: theta_value
        type: list[float]
      - name: baseMVA
        type: float
      - name: bus_num_to_idx
        type: object
    outputs:
      - name: line_flows
        type: list[object]
        description: "List of {from, to, flow_MW, limit_MW, loading_pct} dicts; from/to are raw bus numbers, not indices."

  - name: rank-loading
    description: >
      Sort `line_flows` by `loading_pct` descending and take the top N
      (typically N=3 for dispatch reports). Preserve raw `from`/`to` bus
      numbers — reports refer to power-system bus IDs, not array indices.
    depends_on: [compute-line-flows]
    inputs:
      - name: line_flows
        type: list[object]
    outputs:
      - name: most_loaded_lines
        type: list[object]
        description: "Top-N {from, to, loading_pct} dicts, sorted by loading_pct desc."

scenarios:
  - need: "Compute base-case line loadings on IEEE 14-bus to identify congestion."
    action: "Run load-network → build-bus-index → build-b-matrix → set-up-angle-constraints, then solve the power-balance system with no generation cost (or with dispatch from a sibling step) → compute-line-flows → rank-loading."
    outcome: "List of every branch with MW flow and % of RATE_A; top-3 ranked for the report."
  - need: "DC OPF on MATPOWER case300 where bus numbers are non-contiguous."
    context: "case300 has bus IDs that skip values; `idx = bus_num - 1` would index wrong rows and corrupt B."
    action: "build-bus-index is mandatory; pass `bus_num_to_idx` to every step that walks branch endpoints, including compute-line-flows."
    outcome: "B matrix and flows are correct; report's from/to fields hold true bus numbers."
  - need: "Add transmission thermal limits to an LP that already enforces power balance."
    action: "Reuse `branch_susceptances` from build-b-matrix and the existing `theta` variables; call enforce-thermal-limits to append 2·n_branch linear constraints."
    outcome: "Solver returns dispatch that respects RATE_A on every branch with a positive rate."

anti_patterns:
  - "Indexing branch endpoints as `br[0] - 1` instead of `bus_num_to_idx[int(br[0])]`. Breaks on any case with non-contiguous bus IDs (case300, real utility models)."
  - "Forgetting to constrain the slack-bus angle to 0. The B matrix is singular without a reference; the solver will fail or return arbitrary angles."
  - "Mixing units: writing `Pg - Pd = B @ theta` with Pg/Pd in MW. The right-hand side is in per-unit; divide loads/generation by `baseMVA` before equating."
  - "Including AC effects (line resistance, reactive power, voltage magnitude). DC power flow is lossless and assumes V = 1.0 pu — adding them silently breaks the linearization."
  - "Dividing by zero on x = 0 branches. Skip them (susceptance 0) instead of letting `1/x` blow up."
  - "Reporting array indices as bus IDs. The report consumer expects raw MATPOWER bus numbers; convert back via the bus mapping before emitting JSON."
```
