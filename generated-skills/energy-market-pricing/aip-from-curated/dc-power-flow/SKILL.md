---
name: dc-power-flow
description: "DC power flow analysis for power systems. Use when computing power flows using DC approximation, building susceptance matrices, calculating line flows and loading percentages, or performing sensitivity analysis on transmission networks."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Linearized (DC) power flow on a MATPOWER-format transmission network:
  build the susceptance matrix B from branch reactances, locate the slack
  bus, formulate per-bus power balance, compute branch flows and loading
  percentages, and emit linear thermal-limit constraints suitable for
  DC-OPF. DC assumes lossless lines (R≈0), flat voltage (|V|=1 pu), and
  small angles (sin θ ≈ θ, cos θ ≈ 1), so flow depends only on bus angles
  θ and line reactance X. Handles non-contiguous MATPOWER bus numbering
  via an explicit bus-number-to-index mapping.

trigger_when:
  - User asks to compute power flow using the DC approximation.
  - Building a susceptance matrix (B) from branch reactances.
  - Calculating line flows or loading percentages on a transmission network.
  - Setting up linear constraints for a DC-OPF formulation (power balance, slack reference, thermal limits).
  - Sensitivity or "what-if" analysis on a transmission constraint (e.g., relaxing a thermal limit and re-clearing the market).
  - Composing DC power flow as the network model inside economic dispatch or LMP calculations.

do_not_use_when:
  - Full AC power flow is required (voltage magnitude profile, reactive power, Ohmic losses).
  - The analysis depends on modeling line resistance, Q injections, or |V| deviations explicitly.

steps:
  - name: load-network-data
    description: >
      Read the MATPOWER-format snapshot into NumPy arrays. `buses` rows have
      bus number in column 0 and bus type in column 1 (type 3 = slack).
      `branches` rows have from/to bus numbers in columns 0/1, reactance X
      in column 3, and RATE_A (MW thermal limit) in column 5. `baseMVA` is
      the per-unit base used to convert between pu and MW.
    outputs:
      - name: buses
        type: object
        description: 2D NumPy array of bus rows (MATPOWER format).
      - name: branches
        type: object
        description: 2D NumPy array of branch rows (MATPOWER format).
      - name: baseMVA
        type: float
        description: System base power for pu conversion (MW per pu).

  - name: build-susceptance-matrix
    description: >
      Build the n_bus x n_bus B matrix, the per-branch susceptance list, and
      the bus-number-to-index map. Diagonal B[i,i] = sum of incident
      susceptances; off-diagonal B[f,t] = B[t,f] = -1/X. Branches with X==0
      contribute susceptance 0 and are skipped in the matrix update.
    script: scripts/build_b_matrix.py
    inputs:
      - name: branches
        type: object
      - name: buses
        type: object
    outputs:
      - name: B
        type: object
        description: n_bus x n_bus symmetric susceptance matrix.
      - name: branch_susceptances
        type: list[float]
        description: Susceptance b = 1/X for each branch, in branch order; 0 when X==0.
      - name: bus_num_to_idx
        type: object
        description: dict mapping bus_number -> 0-indexed row position. Required for all downstream bus indexing — bus numbers are not guaranteed contiguous (e.g., case300).

  - name: identify-slack-bus
    description: >
      Locate the slack bus (the row with `buses[i, 1] == 3`) and return its
      0-indexed position. Downstream solvers must anchor θ[slack_idx] = 0;
      without this reference B is singular.
    script: scripts/build_b_matrix.py
    inputs:
      - name: buses
        type: object
    outputs:
      - name: slack_idx
        type: integer

  - name: formulate-power-balance
    description: >
      For every bus i, enforce `Pg_i - Pd_i = B[i, :] @ θ` (all in pu;
      convert MW values with `Pg_pu = Pg_MW / baseMVA`). θ is a length-n_bus
      vector of bus voltage angles in radians. Add the slack reference
      constraint `θ[slack_idx] == 0`. In a power-flow-only mode with fixed
      Pg/Pd, solve the resulting linear system for θ; in DC-OPF, treat Pg as
      a decision variable and let the LP/QP solver pick it.
    inputs:
      - name: B
        type: object
      - name: slack_idx
        type: integer

  - name: compute-line-flows
    description: >
      For each branch, flow_pu = b * (θ_f - θ_t) with f, t looked up via
      `bus_num_to_idx`; then flow_MW = flow_pu * baseMVA. Loading percent =
      |flow_MW| / RATE_A * 100, guarded by RATE_A > 0 (set to 0 otherwise).
      Returns one dict per branch with from, to, flow_MW, limit_MW, loading_pct.
    script: scripts/build_b_matrix.py
    inputs:
      - name: branches
        type: object
      - name: branch_susceptances
        type: list[float]
      - name: theta
        type: object
        description: Length-n_bus vector of bus angles (radians) — either solved or symbolic, depending on mode.
      - name: baseMVA
        type: float
      - name: bus_num_to_idx
        type: object
    outputs:
      - name: line_flows
        type: list[object]
        description: One dict per branch — keys from, to, flow_MW, limit_MW, loading_pct.

  - name: enforce-thermal-limits
    description: >
      For DC-OPF: per branch, add the linear constraint pair
      `flow_MW <= RATE_A` and `flow_MW >= -RATE_A`, where
      `flow_MW = b * (θ_f - θ_t) * baseMVA`. Skip branches with RATE_A == 0
      (unlimited). Binding branches in the solution are those with
      |flow_MW| / RATE_A >= ~0.99 — surface them for congestion analysis.
    inputs:
      - name: branches
        type: object
      - name: branch_susceptances
        type: list[float]
      - name: baseMVA
        type: float
      - name: bus_num_to_idx
        type: object

modes:
  - name: power-flow-only
    body: >
      Given fixed Pg and Pd (vectors in pu), solve B·θ = (Pg - Pd) with
      θ[slack_idx] = 0 for θ, then call compute-line-flows. No optimization
      involved.
  - name: dc-opf
    body: >
      Treat Pg as a decision variable. Add per-bus power balance, the slack
      reference, and per-branch thermal limits as linear constraints. The
      LP/QP solver minimizes total cost subject to these network
      constraints plus generator-limit and reserve constraints from
      neighboring procedures.

integrations:
  - partner: economic-dispatch
    body: >
      DC-OPF mode supplies the network constraints (B, slack reference,
      thermal limits) that the economic dispatch LP layers on top of
      generator cost and limit constraints.
  - partner: locational-marginal-prices
    body: >
      LMPs are the duals of the per-bus power balance constraint formulated
      in `formulate-power-balance`. Binding thermal limits surfaced in
      `enforce-thermal-limits` drive the LMP spread between buses.

scenarios:
  - need: Susceptance matrix for IEEE case300 where bus numbers are non-contiguous (e.g., 9001–9051).
    context: Indexing with `bus_number - 1` would either overflow array bounds or write to the wrong row.
    action: Build `bus_num_to_idx` first; use it to translate every branch endpoint before indexing B.
    outcome: B is correctly assembled and symmetric; downstream flows match reference values.

  - need: Day-ahead market what-if — raise the thermal capacity of branch (64 → 1501) by 20% and re-clear.
    context: Base case shows congestion suspected on a single line; counterfactual isolates the effect of that one constraint.
    action: Build B and constraints once, then rerun DC-OPF with the modified RATE_A on the target branch; compare LMPs and binding-line sets.
    outcome: Delta LMPs and the congestion-relieved flag attribute price impact to the single transmission constraint.

  - need: Quick power flow check given a known dispatch.
    context: Pg/Pd are fixed; no optimization required.
    action: Use `power-flow-only` mode — solve B·θ = (Pg - Pd) with θ[slack] = 0, then run compute-line-flows.
    outcome: Per-branch MW flows and loading percentages without invoking an LP solver.

anti_patterns:
  - Indexing B or branch endpoints with `bus_number - 1`. Bus numbers are not guaranteed contiguous (case300 is a classic counterexample). Always route through `bus_num_to_idx`.
  - Forgetting to anchor θ at the slack bus. Without `θ[slack_idx] == 0`, B is singular and θ is underdetermined.
  - Treating reactance X as susceptance. Susceptance b = 1 / X, not X. Guard X == 0 before dividing.
  - Reading the wrong MATPOWER columns. Reactance X is branch column 3; RATE_A (thermal limit, MW) is branch column 5. Bus type is bus column 1; bus number is bus column 0.
  - Dividing by RATE_A without guarding RATE_A == 0 when computing loading_pct (set to 0 instead).
  - Mixing units inside the constraint. Either work entirely in pu, or multiply by baseMVA before adding MW-denominated thermal limits — don't compare a pu flow against a MW rating.
  - Using DC flow output to reason about voltage magnitudes, reactive power, or losses — DC assumes |V| = 1 pu and ignores Q and R.
```
