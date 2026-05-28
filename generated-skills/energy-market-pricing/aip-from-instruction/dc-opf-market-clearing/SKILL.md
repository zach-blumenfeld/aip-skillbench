---
name: dc-opf-market-clearing
description: Solve single-period DC-OPF with reserve co-optimization on a MATPOWER-format network, then re-solve under a counterfactual where one or more transmission line thermal capacities are scaled. Produces locational marginal prices (LMPs), reserve market clearing price (MCP), binding lines, total system cost, and an impact-analysis comparison. Use when the task mentions DC-OPF, day-ahead market clearing, reserve co-optimization, LMP, congestion analysis, transmission "what-if" line capacity changes, or MATPOWER networks. Not for AC-OPF, unit commitment, or multi-period dispatch.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Compute market-clearing results for a MATPOWER-format power system under
  DC-OPF with reserve co-optimization (energy and spinning reserve cleared
  jointly with standard capacity coupling). Re-solve under a counterfactual
  where one or more branch thermal capacities are scaled, then emit the
  comparison report.json described in the task: base and counterfactual
  total cost, per-bus LMPs, reserve MCP, binding lines, and an
  impact_analysis block (cost reduction, top-3 LMP drops, whether the
  modified line is still binding).

trigger_when:
  - Task input is a MATPOWER-format power system (network.json with bus/gen/branch/gencost) and asks to compute LMPs, reserve MCP, total cost, or binding lines.
  - Task describes a "what if we relax / increase / decrease this line's thermal capacity" counterfactual against a base case.
  - User mentions DC-OPF, day-ahead market clearing, reserve co-optimization with capacity coupling, or transmission congestion analysis.
  - Task instruction prescribes a report structure with `base_case`, `counterfactual`, `impact_analysis` blocks.

do_not_use_when:
  - The task requires AC-OPF (voltage magnitudes, reactive dispatch, line losses).
  - The task requires unit commitment (binary on/off, startup/shutdown costs, ramp constraints across periods).
  - The task is multi-period chronological dispatch, storage scheduling, or stochastic/robust OPF.
  - The input is not in MATPOWER conventions and would need a separate parser (e.g., PSS/E raw files, PowerWorld aux files).

scope_and_approval: >
  Read-only on the input network file (uses a deep copy when applying the
  counterfactual so the base solve is reproducible). Writes only to the
  output report.json path the user names. No network calls. Safe to run
  repeatedly with different overrides.

steps:
  - name: read-instruction
    description: From the task prompt, extract (a) the network file path, (b) the counterfactual branch identified by from-bus and to-bus, (c) the capacity scaling factor (e.g., +20% → factor 1.2), (d) the output report path, and (e) any non-default binding threshold (the task spec uses 99% — 0.99).
  - name: inspect-network
    description: >
      Open the network file. Confirm it has top-level `bus`, `gen`, `branch`,
      `gencost` (unwrap a top-level `mpc` key if present, as some exporters
      nest the network under that name). Scan the branch list for the
      counterfactual pair in either direction; if more than one match
      exists, decide whether to apply the override to all parallel branches
      or to one specific row (use `--branch-index` for the latter). Note
      whether the file carries a `reserves` block — if not, the solver
      defaults reserve requirement to the largest in-service generator's
      Pmax (N-1).
  - name: ensure-deps
    description: Ensure numpy and scipy are importable. The solver script declares them in a PEP 723 header, so `uv run scripts/solve_dcopf.py …` resolves them automatically. If invoking with plain `python`, install with `pip install numpy scipy` first.
  - name: solve-and-write-report
    description: Run the solver once with both the base and counterfactual settings. Example, `uv run scripts/solve_dcopf.py network.json --override-line 64,1501,1.2 --report report.json`. The script solves the base case, applies the override on a deep copy, solves the counterfactual, computes the impact-analysis block, and writes report.json in the schema the task requires.
  - name: sanity-check
    description: Open the produced report.json and verify — (1) solver did not error; (2) `base_case.binding_lines` includes the line you targeted (otherwise the counterfactual is not a meaningful relief test — surface this to the user); (3) `counterfactual.total_cost_dollars_per_hour` ≤ `base_case.total_cost_dollars_per_hour`; (4) `impact_analysis.cost_reduction_dollars_per_hour` equals base − counterfactual to 4 decimal places; (5) `congestion_relieved` is consistent with whether the targeted line still appears in `counterfactual.binding_lines`.
  - name: handle-edge-cases
    description: >
      If LMPs come back with median strongly negative, the solver's
      dual-sign auto-correct already flipped them — no action needed; if
      values still look inverted, consult `references/dcopf-formulation.md`.
      If the solver reports infeasibility, do NOT silently relax
      constraints. Read the error, then consult the `decisions` table and
      `references/dcopf-formulation.md` to diagnose — the most common
      causes are a reserve requirement that exceeds total generator
      headroom, or a counterfactual that created a disconnected island.

decisions:
  - signal: Network file has no `reserves` field.
    action: Use defaults — reserve requirement = largest in-service Pmax (N-1 contingency), per-gen reserve cap = Pmax − Pmin, reserve offer cost = 0. The solver does this automatically; document the assumption when reporting results.
  - signal: Network file has a `reserves` field with `req` (scalar or list).
    action: Use the supplied values. The solver reads them automatically. If `req` is a list of zonal requirements, the solver currently sums them into a single system requirement — flag this to the user if zonal MCPs are needed.
  - signal: Multiple branches share the named (from, to) pair (parallel lines).
    action: Default behavior scales rateA on all of them. If the user wants exactly one line modified, pass `--branch-index N` (0-indexed across status=1 branches in MATPOWER order).
  - signal: The counterfactual target branch has rateA = 0 in MATPOWER (unlimited).
    action: Scaling is a no-op. The solver warns on stderr. Surface this to the user — pick a different branch or recheck the task identifiers.
  - signal: Generator cost is quadratic (gencost model 2, n ≥ 3 with non-zero quadratic coefficient).
    action: The solver linearizes at the midpoint of [Pmin, Pmax] to keep the LP clean. For most networks this matches the LMPs an LP-based market would publish. If high precision is required at extreme dispatches, re-linearize at the solution and re-solve — see `references/dcopf-formulation.md`.
  - signal: Binding threshold not specified in the task.
    action: Use the task-spec default of 0.99 (line counts as binding when |flow| ≥ 99% of rateA).
  - signal: Solver returns a non-`optimal` status.
    action: >
      Stop. Do not write a partial report. Write a JSON object with a top-level
      `status` field set to `infeasible` and a `message` field carrying the
      solver text, then surface the failure to the user.
  - signal: After running the counterfactual, the targeted line still binds at ≥ 99%.
    action: Set `congestion_relieved` to false. A capacity increase does not guarantee relief — at +20% a line may still saturate. The script handles this correctly.

scenarios:
  - need: "Task: relax the line connecting bus 64 to bus 1501 by 20% and report the impact on yesterday's day-ahead clearing."
    context: network.json is in MATPOWER form. Reserve data is either embedded or defaults to N-1. The task spec's binding threshold is 99%.
    action: |
      uv run scripts/solve_dcopf.py network.json --override-line 64,1501,1.2 --report report.json
    outcome: A single report.json with base_case, counterfactual, and impact_analysis populated. Sanity checks pass when base_case.binding_lines includes the (64,1501) line and counterfactual total cost ≤ base total cost.
  - need: There are two parallel branches between buses 64 and 1501 and the task only refers to one of them.
    context: Inspect `network["branch"]` to find both rows, note their indices among status=1 entries, and decide which one the task means (typically the lower-impedance / higher-capacity one is the binding constraint).
    action: |
      uv run scripts/solve_dcopf.py network.json --override-line 64,1501,1.2 --branch-index 42 --report report.json
    outcome: Only branch row 42 has its rateA scaled; the other parallel branch is untouched.
  - need: Network has no `reserves` block but the task still asks for a reserve MCP.
    action: Run with defaults. The solver imposes a system reserve requirement equal to the largest in-service Pmax. The resulting reserve_mcp_dollars_per_MWh is the shadow price of that constraint; report 0 when it is non-binding.
    outcome: Report contains a non-zero reserve MCP only when the reserve constraint is active at the LP optimum.

anti_patterns:
  - Solving AC-OPF when the task says DC-OPF. The two produce different LMPs, different binding constraints, and different MCPs.
  - Treating an LMP as just the marginal generator cost. With congestion, LMPs differ by bus; with reserve coupling, dispatched marginal cost shifts because energy and reserve compete for the same capacity.
  - Hard-coding the slack bus to bus index 0 or bus number 1. Read the bus `type` field — `type == 3` marks the slack/reference.
  - Mutating the input network dict in place when applying the counterfactual. Always operate on a deep copy so the base solve remains reproducible. The solver script does this; do not bypass it.
  - Reporting `congestion_relieved` as true simply because the line capacity was increased. The flag is derived from whether the line is binding in the counterfactual — at +20% it may still saturate.
  - Rounding LMPs or costs before sorting `buses_with_largest_lmp_drop`. Sort on full-precision deltas; round only at output time. The solver script handles this.
  - Dropping the capacity-coupling constraint `p_g + r_g ≤ Pmax`. Without it, energy and reserve markets decouple, the reserve MCP collapses to zero, and energy LMPs come back too low.
  - Setting `binding_lines` to "the line with the highest absolute flow." Binding requires loading ≥ threshold (default 99%); a heavily-loaded but unconstrained line is not binding.
  - Silently relaxing an infeasible LP (e.g., dropping the reserve requirement when no generator can meet it). Surface the infeasibility and ask the user — never fabricate clearing prices.

modes:
  - name: full
    body: >
      Solve base + counterfactual in one invocation and write the
      full report.json. This is the default and matches the task spec.
      Example, `uv run scripts/solve_dcopf.py network.json
      --override-line 64,1501,1.2 --report report.json`.
  - name: base-only
    body: >
      Solve just the base case for sanity checking the network or
      identifying which lines bind before designing a counterfactual.
      Example, `uv run scripts/solve_dcopf.py network.json --report base.json`
      (omit --override-line). The output contains only `base_case`.
  - name: custom-reserve
    body: >
      Override the system reserve requirement when the task supplies it
      or when the N-1 default is inappropriate. Example,
      `--reserve-req 500` sets the requirement to 500 MW.

search_shortcuts:
  - category: Solver dependencies
    body: >
      numpy and scipy (HiGHS LP solver bundled with scipy >= 1.11). Both
      declared in the script's PEP 723 header, so `uv run` resolves
      automatically. For pip, `pip install numpy scipy`.
  - category: Useful references
    body: >
      `references/matpower-format.md` for column layouts and field gotchas;
      `references/dcopf-formulation.md` for the LP and dual sign
      conventions; `references/report-template.md` for the exact output
      schema and rounding rules.
```
