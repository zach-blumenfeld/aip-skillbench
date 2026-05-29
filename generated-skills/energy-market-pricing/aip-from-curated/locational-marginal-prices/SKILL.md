---
name: locational-marginal-prices
description: "Extract locational marginal prices (LMPs) from DC-OPF solutions using dual values. Use when computing nodal electricity prices, reserve clearing prices, or performing price impact analysis."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Turn a solved DC-OPF + reserve co-optimization into the priced view a
  market analyst needs: per-bus LMPs (in $/MWh) from the bus power-balance
  duals, the system reserve MCP from the reserve-requirement dual, and the
  list of binding transmission lines. Also drive a base-vs-counterfactual
  workflow that perturbs a single transmission limit, re-solves, and emits
  the `impact_analysis` block (cost reduction, top-N LMP drops, congestion
  relief) the energy-market-pricing task's `report.json` requires. Encodes
  the per-unit -> $/MWh scaling, the LMP sign convention, the 99% binding
  threshold, and the dual-extraction protocol (store the constraint
  reference BEFORE solve, read `.dual_value` AFTER).

trigger_when:
  - Extracting nodal LMPs from a CVXPY DC-OPF solution.
  - Computing the system-wide reserve clearing price (reserve MCP).
  - Identifying binding transmission lines (>= 99% loading).
  - Running a counterfactual where a line's `rateA` is scaled and the impact
    on cost / LMPs / congestion is reported.
  - Building the `report.json` artifact for the energy-market-pricing task
    (base case, counterfactual, impact_analysis blocks).
  - Investigating negative LMPs, large LMP separation, or unexpected zero
    duals after a solve.

do_not_use_when:
  - Constructing the DC-OPF cost-minimization problem itself or its
    generation/reserve variables — use the `economic-dispatch` skill.
  - Computing line flows for power-flow analysis without economic context —
    use the `dc-power-flow` skill.
  - Parsing MATPOWER network data (bus/gen/branch arrays, baseMVA, bus
    number maps) — use the `power-flow-data` skill.

scope_and_approval: >
  Read-only on the solved problem (duals and `.value` attributes are
  inspected, never mutated). The counterfactual perturbation is performed
  on an in-memory COPY of the branch array via `perturb_line_limit`; the
  original numpy arrays and the source `network.json` are left untouched.
  No filesystem writes except the final `report.json` the caller assembles.

steps:
  - name: wire-balance-constraint-refs
    description: >
      During DC-OPF construction, store each bus's power-balance equality
      constraint in a Python list IN THE SAME ORDER as the bus array's row
      order, AND record the corresponding MATPOWER bus number (column 0 of
      the bus array) in a parallel list. The dual extraction step keys on
      this ordering. Without these stored references, `dual_value` is
      unreachable after `prob.solve()` — CVXPY only exposes duals through
      the original constraint objects.
    outputs:
      - name: balance_constraints
        type: list[object]
        description: One cp.Constraint per bus, in bus-array row order.
      - name: bus_numbers
        type: list[integer]
        description: MATPOWER bus numbers parallel to balance_constraints.

  - name: wire-reserve-constraint-ref
    description: >
      Store the system reserve-requirement constraint
      (`cp.sum(Rg) >= reserve_requirement`) as a named variable BEFORE
      appending it to the problem's constraint list. The reserve MCP is the
      dual of this exact object.
    outputs:
      - name: reserve_con
        type: object
        description: The cp.Constraint enforcing total reserve >= requirement.

  - name: solve
    description: >
      Call `prob.solve(solver=cp.CLARABEL)` (or another conic LP solver that
      returns duals). Confirm `prob.status == "optimal"` before reading any
      dual or `.value` — non-optimal solves yield `None` duals and the
      downstream extraction silently fills in zeros.
    inputs:
      - name: prob
        type: object
        description: The fully-constrained cp.Problem.

  - name: extract-lmps
    description: >
      Read each balance constraint's `dual_value` and scale by `baseMVA` to
      convert from $/pu-MW to $/MWh. Returns one
      `{bus, lmp_dollars_per_MWh}` dict per bus in the exact shape the task's
      `lmp_by_bus` field expects. Preserves sign (negative LMPs are valid;
      see `references/pricing-concepts.md` § 2).
    script: scripts/lmp_utils.py
    inputs:
      - name: balance_constraints
        type: list[object]
      - name: bus_numbers
        type: list[integer]
      - name: baseMVA
        type: float
    outputs:
      - name: lmp_by_bus
        type: list[object]
        description: List of {bus, lmp_dollars_per_MWh}, one per bus.

  - name: extract-reserve-mcp
    description: >
      Read `reserve_con.dual_value` and return it directly (no baseMVA
      scaling — `Rg` and `reserve_requirement` are already in MW under the
      PGLib reserve extension). Coerces `None` (unsolved / inactive) to 0.0.
    script: scripts/lmp_utils.py
    inputs:
      - name: reserve_con
        type: object
    outputs:
      - name: reserve_mcp_dollars_per_MWh
        type: float

  - name: find-binding-lines
    description: >
      Compute DC line flow `flow_MW = (1/x) * (theta[f] - theta[t]) *
      baseMVA` for every in-service branch, divide by `rateA`, and emit a
      list of lines at >= 99% loading. Skips branches with `x == 0`,
      `rateA == 0`, or `status == 0`. Pass `theta.value` (the solved numpy
      array) — passing the cvxpy Variable directly raises.
    script: scripts/lmp_utils.py
    inputs:
      - name: branches
        type: object
        description: numpy array, network['branch'].
      - name: theta_values
        type: object
        description: numpy array, `theta.value` after solve.
      - name: baseMVA
        type: float
      - name: bus_num_to_idx
        type: object
        description: dict bus_number -> 0-indexed row (from power-flow-data).
    outputs:
      - name: binding_lines
        type: list[object]
        description: List of {from, to, flow_MW, limit_MW}.

  - name: assemble-case-snapshot
    description: >
      Bundle the four scalars/lists from this case into the per-case dict
      `{total_cost_dollars_per_hour, lmp_by_bus, reserve_mcp_dollars_per_MWh,
      binding_lines}`. `total_cost_dollars_per_hour` is `float(prob.value)`
      — already in dollars (no baseMVA scaling) because the objective is
      built from gencost coefficients in $/MWh against MW-valued Pg. This is
      the `base_case` block (or `counterfactual` block) of `report.json`.
    inputs:
      - name: prob
        type: object
      - name: lmp_by_bus
        type: list[object]
      - name: reserve_mcp_dollars_per_MWh
        type: float
      - name: binding_lines
        type: list[object]
    outputs:
      - name: case_snapshot
        type: object

  - name: perturb-line-limit
    description: >
      Counterfactual setup. Returns a deep copy of `branches` with the
      target line's `rateA` (column 5) scaled by `factor`. Matches the line
      in EITHER direction (from->to or to->from) so the order of bus IDs in
      the task prompt does not matter. Raises if no matching branch exists
      — a silent no-op would invalidate the entire counterfactual analysis.
    script: scripts/lmp_utils.py
    inputs:
      - name: branches
        type: object
      - name: target_from
        type: integer
      - name: target_to
        type: integer
      - name: factor
        type: float
        description: e.g. 1.20 for a 20% rating increase.
    outputs:
      - name: perturbed_branches
        type: object
      - name: row_index_modified
        type: integer

  - name: resolve-counterfactual
    description: >
      Rebuild the DC-OPF + reserve co-optimization on `perturbed_branches`
      (re-running steps `wire-balance-constraint-refs`,
      `wire-reserve-constraint-ref`, `solve`, `extract-lmps`,
      `extract-reserve-mcp`, `find-binding-lines`, `assemble-case-snapshot`).
      Use a FRESH cp.Problem and FRESH constraint-reference lists — reusing
      base-case constraint objects against new data will either error or
      silently return stale duals. The susceptance matrix `B` depends only
      on `x` (not `rateA`), so it may be reused; only line ratings changed.
    inputs:
      - name: perturbed_branches
        type: object
    outputs:
      - name: cf_case_snapshot
        type: object

  - name: compute-impact
    description: >
      Compare `base_case` and `counterfactual` snapshots and emit the
      `impact_analysis` block: cost reduction (base - cf), the top-N buses
      ranked by most-negative `cf_lmp - base_lmp` (NOT by absolute
      magnitude), and `congestion_relieved = was_binding_in_base AND NOT
      is_binding_in_cf` for the perturbed line. Default N is 3 to match the
      task spec.
    script: scripts/lmp_utils.py
    inputs:
      - name: base_case
        type: object
      - name: counterfactual
        type: object
      - name: target_from
        type: integer
      - name: target_to
        type: integer
    outputs:
      - name: impact_analysis
        type: object

  - name: assemble-report
    description: >
      Write `report.json` at the task's expected path:
      `{base_case, counterfactual, impact_analysis}`. No reshaping — each
      block is already in the task's target schema. Round-trip through
      `json.dumps(..., indent=2)` to keep the artifact diff-friendly.
    inputs:
      - name: base_case
        type: object
      - name: counterfactual
        type: object
      - name: impact_analysis
        type: object
    outputs:
      - name: report_path
        type: string

  - name: load-pricing-reference-when-stuck
    description: >
      If a result looks wrong — LMP off by 100×, negative MCP, "largest
      drop" ranking dispute, `cost_reduction < 0`, or `congestion_relieved`
      not what you expected — read `references/pricing-concepts.md` for the
      sign conventions, scaling rules, and economic intuition before
      patching the calculation.

scenarios:
  - need: >
      Build `report.json` for the energy-market-pricing task: base vs
      counterfactual where line 64 <-> 1501 has `rateA` increased by 20%.
    context: >
      `power-flow-data` has produced `network`, `bus_num_to_idx`, and the
      bus-number list. `economic-dispatch` has built the DC-OPF + reserve
      co-optimization for the base case.
    action: >
      Wire constraint refs -> solve -> extract LMPs, reserve MCP, binding
      lines -> snapshot. Then `perturb_line_limit(branches, 64, 1501, 1.20)`
      -> rebuild + re-solve -> snapshot. Then `compute_impact_analysis(base,
      cf, 64, 1501)` -> assemble and write `report.json`.
    outcome: >
      `report.json` matches the task schema exactly. `cost_reduction >= 0`,
      `congestion_relieved == True` if line 64-1501 was binding in base and
      cleared in CF, and `buses_with_largest_lmp_drop` holds three entries
      ranked by most-negative delta.

  - need: >
      A bus reports a large negative LMP (e.g. -$3000/MWh).
    context: >
      Cheap generation is trapped behind a congested line; adding load at
      that bus would consume the trapped MW and avoid expensive redispatch.
    action: >
      Report the LMP verbatim — do not clip or absolute-value. Cross-check
      that `find_binding_lines` flags at least one adjacent line. If yes,
      the negative LMP is the expected congestion signal.
    outcome: >
      The report carries the negative LMP. A reader of
      `references/pricing-concepts.md` § 2 can confirm it is physically
      valid, not a sign bug.

  - need: >
      The target line is NOT binding in the base case.
    context: >
      Relaxing a non-binding constraint has no effect on the optimum.
    action: >
      Still run the counterfactual end-to-end. `cost_reduction` will be
      ~0 (within solver tolerance), `lmp_by_bus` will be unchanged, and
      `congestion_relieved` will be False (the precondition
      `was_binding_in_base` fails).
    outcome: >
      `report.json` reflects the no-op honestly; do not synthesize a
      different perturbation to manufacture an effect.

anti_patterns:
  - Reading `constraint.dual_value` BEFORE calling `prob.solve()` — duals
    are `None` until the solver populates them. The utility coerces None to
    0.0 so the report shape is preserved, but every price will be zero.
  - Forgetting `* baseMVA` when scaling balance duals. LMPs come out in
    $/pu-MW, ~100× too small for baseMVA=100 networks.
  - Scaling the reserve MCP by baseMVA. The reserve constraint is already
    in MW, so multiplying by baseMVA inflates the MCP ~100×.
  - Taking `abs()` of LMPs or clipping at zero. Negative LMPs are valid
    congestion signals; clipping discards the very thing the report needs.
  - Mutating `branches` in place between the base and counterfactual solves
    so the "base case" silently re-runs with perturbed data. Always use
    `perturb_line_limit`, which copies.
  - Matching the target line in only one direction (`from == 64 and to ==
    1501`) and missing the case where the file stores it as 1501 -> 64.
  - Ranking `buses_with_largest_lmp_drop` by `abs(delta)` instead of most-
    negative `delta`. Absolute-magnitude ranking pollutes the list with
    buses whose LMPs ROSE, which is the opposite of what the task asks for.
  - Reusing the base-case cp.Problem / constraint references against the
    perturbed branch array. Either CVXPY raises or duals come back stale.
    Build a fresh problem with fresh constraint references for the CF.
  - Treating `theta.value[f] - theta.value[t]` as already-in-MW. The DC
    flow formula needs `(1/x) * dtheta * baseMVA`; the `* baseMVA` is the
    same easy-to-miss factor that bites LMP extraction.
  - Skipping the `status == 0` check on branches when scanning binding
    lines. An out-of-service branch will produce nonsensical flow / loading
    numbers and may appear "binding" or "overloaded".
```
