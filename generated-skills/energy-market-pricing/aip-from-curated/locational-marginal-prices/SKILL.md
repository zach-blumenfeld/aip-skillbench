---
name: locational-marginal-prices
description: "Extract locational marginal prices (LMPs) from DC-OPF solutions using dual values. Use when computing nodal electricity prices, reserve clearing prices, or performing price impact analysis."
license: MIT
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3 with cvxpy (CLARABEL solver) and numpy. Helpers in scripts/lmp_ops.py.
---

```yaml
purpose: >
  Extract locational marginal prices (LMPs), the reserve market-clearing
  price, and binding transmission lines from a solved DC-OPF
  (optionally with reserve co-optimization), and run "what if we relax
  this line?" counterfactual analyses that quantify cost reduction and
  per-bus LMP changes. LMPs ARE the dual values (shadow prices) of the
  per-bus power-balance constraints, so the central discipline this
  skill enforces is "store the constraint object before solving, then
  read `dual_value` after solving" — without that handle the duals are
  unreachable. Per-unit scaling (multiply by `baseMVA`), the
  sign-convention for negative LMPs, the 99 %-loading binding-line
  threshold, and the bidirectional from/to line lookup all live in
  `scripts/lmp_ops.py` so the rules are applied identically in the base
  and counterfactual cases. Authored for the SkillsBench
  energy-market-pricing task but applies to any DC-OPF nodal-pricing
  problem.

trigger_when:
  - Computing nodal electricity prices (LMPs) from a DC-OPF or DC-OPF + reserves solution.
  - Producing a market-clearing report that includes LMPs, reserve MCP, and binding lines.
  - Performing a counterfactual "what if we relax this transmission constraint?" analysis.
  - Identifying congested transmission lines (loading at or above 99 % of thermal limit).
  - User mentions LMP, locational marginal price, nodal price, shadow price, dual variable of a balance constraint, reserve clearing price, MCP, binding line, congestion-relief analysis, counterfactual market clearing.

do_not_use_when:
  - The pricing problem is AC-OPF or any full nonlinear OPF — dual semantics and per-unit scaling differ, and this skill's helpers assume the linear DC formulation.
  - The model has no explicit per-bus power-balance constraint (e.g. a single system-wide energy balance) — LMPs are not separable per bus.
  - A solved problem object is not available — these helpers read `dual_value` off CVXPY constraints that already went through `prob.solve()`.

scope_and_approval: >
  Read-only on input data. Mutates the in-memory MATPOWER `branch`
  matrix only via `modify_line_limit` (and only for the counterfactual
  run); the caller is expected to either re-load the network for the
  base case or pass a deep copy. No file writes, no network access, no
  destructive operations. Safe to run without prompting.

steps:
  - name: build-and-store-balance-constraints
    description: >
      Construct the per-bus DC power-balance constraint AS A NAMED OBJECT
      (`balance_con = pg_at_bus - pd == B[i, :] @ theta`, all in per-unit
      with loads divided by `baseMVA`), append it to BOTH the problem
      `constraints` list AND a parallel `balance_constraints` list
      indexed in the same order as the bus rows. Without this parallel
      list the LMPs are unrecoverable after solve — there is no handle
      to call `.dual_value` on. Track a `bus_nums` list (bus numbers
      from `buses[:, 0]`) in the same order so `extract_lmps` can label
      each price.
    outputs:
      - name: balance_constraints
        type: list[object]
        description: CVXPY constraint objects, one per bus, in bus-row order.
      - name: bus_nums
        type: list[integer]
        description: External bus numbers, same order as `balance_constraints`.
  - name: build-and-store-reserve-constraint
    description: >
      If the model includes reserve co-optimization, construct
      `reserve_con = cp.sum(Rg) >= reserve_requirement` as a named
      object and append it to `constraints`. Keep the reference so
      `extract_reserve_mcp` can read its dual after solve. Skip this
      step if the task is energy-only.
    outputs:
      - name: reserve_con
        type: object
        nullable: true
        description: CVXPY reserve-requirement constraint object, or null if energy-only.
  - name: solve-base-case
    description: >
      Call `prob.solve(solver=cp.CLARABEL)` on the assembled problem.
      CLARABEL exposes duals on the equality balance constraints
      directly. Record the optimal objective value as `base_cost`
      (already in $/h when the cost vector uses MATPOWER's `gencost`
      conventions and generation is in MW — DO NOT also multiply by
      baseMVA here; the per-unit scaling lives only in the LMP step).
    depends_on: [build-and-store-balance-constraints, build-and-store-reserve-constraint]
    outputs:
      - name: base_cost
        type: float
      - name: theta_value
        type: object
        description: Solved bus-angle vector (numpy array or `theta.value`).
  - name: extract-lmps-base
    description: >
      Call `extract_lmps(balance_constraints, bus_nums, baseMVA)`. The
      helper reads each constraint's `dual_value`, multiplies by
      `baseMVA` (per-unit dual → $/MWh), preserves the sign exactly
      (negative LMPs are physically valid in congested networks — DO
      NOT clip or filter them), and returns `[{"bus": int,
      "lmp_dollars_per_MWh": float}, ...]` rounded to two decimals.
    script: scripts/lmp_ops.py
    depends_on: [solve-base-case]
    inputs:
      - name: balance_constraints
        type: list[object]
      - name: bus_nums
        type: list[integer]
      - name: baseMVA
        type: float
    outputs:
      - name: base_lmp_by_bus
        type: list[object]
  - name: extract-reserve-mcp-base
    description: >
      Call `extract_reserve_mcp(reserve_con)`. Returns the dual of the
      reserve-requirement constraint in $/MWh (no `baseMVA` scaling —
      reserves are typically formulated in MW directly). Returns 0.0 if
      the constraint is not present or its dual is unset.
    script: scripts/lmp_ops.py
    depends_on: [solve-base-case]
    inputs:
      - name: reserve_con
        type: object
        nullable: true
    outputs:
      - name: base_reserve_mcp
        type: float
  - name: find-binding-lines-base
    description: >
      Call `find_binding_lines(branches, theta_value, bus_num_to_idx,
      baseMVA, threshold_pct=99.0)`. The helper recomputes each branch's
      flow from `b * (θ_from - θ_to) * baseMVA` (skipping rows with
      `x == 0` or `rate_a <= 0`), compares `|flow| / rate_a * 100` to
      99 %, and emits `{"from", "to", "flow_MW", "limit_MW"}` for every
      binding line. Keep the threshold at 99 % — that is the task's
      definition; only override if a different report format demands it.
    script: scripts/lmp_ops.py
    depends_on: [solve-base-case]
    inputs:
      - name: branches
        type: object
      - name: theta_value
        type: object
      - name: bus_num_to_idx
        type: object
      - name: baseMVA
        type: float
    outputs:
      - name: base_binding_lines
        type: list[object]
  - name: modify-line-for-counterfactual
    description: >
      Call `modify_line_limit(branches, target_from, target_to,
      scale_factor)`. The helper matches the line in either direction
      (`from→to` or `to→from`, because the underlying conductor is
      bidirectional even though MATPOWER's row is directed), multiplies
      column 5 (`rate_a`) by the scale factor in place, and returns the
      modified row index. Raises `LookupError` if no matching branch is
      found. Use this AFTER recording the base case and BEFORE building
      the counterfactual problem; either re-load the network for the
      base case or work on a deep copy so the base solve sees the
      original limits.
    script: scripts/lmp_ops.py
    inputs:
      - name: branches
        type: object
      - name: target_from
        type: integer
      - name: target_to
        type: integer
      - name: scale_factor
        type: float
        description: Multiplier applied to `rate_a`. The task uses 1.20 (a 20 % increase).
    outputs:
      - name: modified_row_index
        type: integer
  - name: solve-counterfactual-and-extract
    description: >
      Rebuild the DC-OPF problem from scratch using the modified
      branches (re-running build-and-store-balance-constraints,
      build-and-store-reserve-constraint, and solve-base-case against
      the new branches array), then re-run extract-lmps-base,
      extract-reserve-mcp-base, and find-binding-lines-base on the new
      solution. The same helpers apply — only the input data changes —
      so the per-unit scaling, sign convention, and 99 % threshold stay
      consistent across the two cases. Record outputs as
      `cf_cost`, `cf_lmp_by_bus`, `cf_reserve_mcp`,
      `cf_binding_lines`.
    depends_on: [modify-line-for-counterfactual]
    outputs:
      - name: cf_cost
        type: float
      - name: cf_lmp_by_bus
        type: list[object]
      - name: cf_reserve_mcp
        type: float
      - name: cf_binding_lines
        type: list[object]
  - name: compute-impact
    description: >
      Call `compute_impact(base_cost, cf_cost, base_lmp_by_bus,
      cf_lmp_by_bus, base_binding_lines, cf_binding_lines, target_from,
      target_to, top_n=3)`. The helper computes cost reduction
      (clamping tiny negatives from solver noise to 0 but leaving
      meaningfully negative values visible for investigation), the
      `top_n` buses with the most negative LMP delta (deterministic
      tie-break by bus number ascending), and the
      `congestion_relieved` flag (True iff the target line was binding
      in the base case but not in the counterfactual — matched in
      either direction).
    script: scripts/lmp_ops.py
    depends_on: [extract-lmps-base, extract-reserve-mcp-base, find-binding-lines-base, solve-counterfactual-and-extract]
    inputs:
      - name: base_cost
        type: float
      - name: cf_cost
        type: float
      - name: base_lmp_by_bus
        type: list[object]
      - name: cf_lmp_by_bus
        type: list[object]
      - name: base_binding_lines
        type: list[object]
      - name: cf_binding_lines
        type: list[object]
      - name: target_from
        type: integer
      - name: target_to
        type: integer
      - name: top_n
        type: integer
        nullable: true
    outputs:
      - name: impact_analysis
        type: object
  - name: assemble-report
    description: >
      Call `assemble_report(base_case, counterfactual, impact_analysis)`
      where each case dict has keys `total_cost_dollars_per_hour`,
      `lmp_by_bus`, `reserve_mcp_dollars_per_MWh`, `binding_lines`.
      Field names must match the task's `report.json` schema exactly;
      the helper centralizes the contract so a rename in one place
      propagates everywhere. The caller is responsible for writing the
      returned dict to `report.json`.
    script: scripts/lmp_ops.py
    depends_on: [compute-impact]
    inputs:
      - name: base_case
        type: object
      - name: counterfactual
        type: object
      - name: impact_analysis
        type: object
    outputs:
      - name: report
        type: object

scenarios:
  - need: >
      Energy-market report comparing a base DC-OPF + reserves clearing
      to a counterfactual where the line connecting bus 64 to bus 1501
      has its thermal limit increased by 20 %.
    context: >
      MATPOWER network loaded from `network.json`. Cost vector uses
      `gencost`; balance constraints written in per-unit; reserve
      requirement is a single system-wide `sum(Rg) >= R_req`. Solver:
      CLARABEL.
    action: >
      Build the problem keeping `balance_constraints` and `reserve_con`
      as parallel handles, solve, run `extract_lmps`,
      `extract_reserve_mcp`, `find_binding_lines` on the base case.
      Call `modify_line_limit(branches, 64, 1501, 1.20)`, rebuild and
      re-solve the problem, re-run all three extractors. Pass both
      cases through `compute_impact` (top_n=3) and `assemble_report`,
      write the result to `report.json`.
    outcome: >
      `report.json` with `base_case`, `counterfactual`, and
      `impact_analysis` blocks matching the task schema, with
      `congestion_relieved` true iff the bus 64 ↔ 1501 line was binding
      in the base case but no longer binding in the counterfactual.
  - need: >
      Operator inspection — "which lines are currently saturating in
      our day-ahead clearing?"
    context: >
      Post-solve DC-OPF with `theta.value` available and the
      MATPOWER-format `branches` matrix in memory.
    action: >
      Call `find_binding_lines(branches, theta.value, bus_num_to_idx,
      baseMVA)` (default threshold 99 %) and present the returned list
      of `{from, to, flow_MW, limit_MW}` records.
    outcome: >
      Concrete list of binding (or near-binding) lines with signed flow
      so the operator sees the direction of congestion. No counterfactual
      needed.
  - need: >
      Why are some LMPs in our solution negative? The pricing team
      thinks the solver is broken.
    context: >
      A bus shows `lmp_dollars_per_MWh = -187.4` in a heavily congested
      pocket. Cheap generation is trapped behind a saturated line.
    action: >
      Confirm the result by inspecting the binding lines around that
      bus (`find_binding_lines`). Do NOT clip the negative price.
      Explain that the dual is signed: at this bus, *adding* load
      relieves congestion by consuming the trapped surplus, so the
      marginal cost of serving one more MW is negative.
    outcome: >
      Negative LMP retained in the report. Magnitudes can reach
      thousands of $/MWh in heavily congested networks — they are
      not solver errors.

anti_patterns:
  - Building balance constraints inline inside the `constraints` list without keeping a parallel `balance_constraints` reference list. The duals are then unreachable after solve and there is no way to recover LMPs without rebuilding and re-solving.
  - Forgetting the `* baseMVA` scaling. The constraint is in per-unit so the raw dual is in $/per-unit-MW; without the scale factor the LMPs come out a factor of ~100 too small (for the typical 100 MVA base).
  - Clipping or filtering negative LMPs to zero or absolute value. Negative LMPs are physically valid and informative in congested systems — they signal where adding load would relieve congestion.
  - Applying `* baseMVA` to the reserve MCP. The reserve requirement is normally written in MW directly, so its dual is already in $/MWh.
  - Solving the base case AFTER modifying the branch matrix in place. The base case then sees the relaxed limit and the cost-reduction comparison is meaningless. Either re-load the network for the base, or take a deep copy of `branches` before calling `modify_line_limit`.
  - Hard-coding a from→to direction when checking whether a line is binding or modifying its limit. MATPOWER branch rows are directed but the physical conductor is bidirectional; match on either ordering.
  - Lowering the binding-line threshold from 99 % to "look for anything heavily loaded" when producing the report. The task's `binding_lines` field is defined at the 99 % threshold; anything else makes the report fail verification.
  - Reusing constraint objects between the base and counterfactual problems. CVXPY constraints are bound to the problem they were added to; rebuild the problem (including fresh balance and reserve constraint lists) for the counterfactual.
```
