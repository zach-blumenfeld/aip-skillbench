---
name: dcopf-reserve-dispatch
description: "DC optimal power flow economic dispatch with spinning-reserve co-optimization on MATPOWER/PGLib-OPF network JSON (bus, gen, branch, gencost, reserve_capacity, reserve_requirement). Use when a grid dispatch operator task asks for least-cost generator dispatch under DC nodal power balance, generator and line thermal limits, and reserve requirements with capacity coupling, and for a report of per-generator output and reserve, total cost/load/generation/reserve, most heavily loaded lines, and operating margin."
compatibility: "python3>=3.9. scripts/dispatch.py imports numpy, scipy, cvxpy (CLARABEL solver, via pip package clarabel; HiGHS/ECOS/SCS used as fallbacks if installed). The inspect subcommand needs only the standard library. If numpy/scipy/cvxpy are missing, the script self-bootstraps a venv with python3 -m venv (Debian/Ubuntu package python3-venv) and pip installs them from PyPI."
---

# DC-OPF Dispatch with Spinning Reserves

## Trigger When

- A task gives a power network snapshot in MATPOWER format (often `network.json`, PGLib-OPF derived) and asks to decide generator dispatches.
- The dispatch must be economically efficient (minimum cost) under DC power balance at each bus, generator Pmin/Pmax, transmission (RATE_A) limits, and/or a system spinning-reserve requirement with capacity coupling (output + reserve ≤ Pmax).
- A `report.json` (or similar) is wanted with per-generator output/reserve, cost/load/generation/reserve totals, the most loaded lines, or the operating margin.
- Broader: economic dispatch, DC-OPF, reserve co-optimization, line loading, or susceptance-matrix work on MATPOWER data.

## Purpose

Turns a MATPOWER network snapshot into a verified least-cost DC-OPF dispatch with co-optimized reserves and the standard dispatch report. It carries the MATPOWER column conventions, the bus-number mapping, the cost-polynomial format, the reserve coupling formulation, the DC flow and loading definitions, and the report arithmetic, as one script that solves, independently re-checks feasibility, and writes the report. That leaves the agent to judge the task statement and deliver the result.

## Workflow

Progress:
- [ ] 1. Read the task statement; locate the input network and output path
- [ ] 2. Decide `requirements_fit` and `matpower_branch_model`
- [ ] 3. Inspect the network (`dispatch.py inspect`)
- [ ] 4. Solve and write the report (`dispatch.py solve`)
- [ ] 5. Branch on the solve exit code
- [ ] 6. Extend the report only if step 2 said so, then `dispatch.py check`
- [ ] 7. Deliver

Before the first script, check that `python3 --version` is 3.9 or newer. `inspect` needs nothing else. `solve` and `check` need numpy, scipy, cvxpy and clarabel. If they are missing, the script creates `~/.cache/dcopf-reserve-dispatch/venv` (override with `DCOPF_VENV=...`), pip installs them, and re-runs itself. That needs `python3-venv` and PyPI access. If the bootstrap fails, name every missing piece from its error message. The first run spends about a minute installing; later runs take about 10 s on a ~3000-bus case. All launch commands below are run from the skill folder. Pass absolute paths for the task files (e.g. `/root/network.json`).

### 1. Task statement (client task)

Read the instruction. Note the container paths of the network file and the requested report file, the report schema, and every constraint and output it names. Never open the network JSON with `cat`/`head`/`sed`: realistic files are 100k+ lines. Load it with Python's `json`, which the scripts already do.

### 2. Requirements decision (decision)

Answer these questions about the task statement in one pass:

```yaml
requirements_fit:
  type: choice
  instructions: >
    Compare the task's required constraints and report fields with what
    `dispatch.py solve` produces: DC nodal balance, Pmin/Pmax, RATE_A line limits,
    reserve <= reserve_capacity, output + reserve <= Pmax, sum(reserve) >= requirement,
    polynomial (degree <= 2) or piecewise-linear cost, and a report with
    generator_dispatch {id, bus, output_MW, reserve_MW, pmax_MW}, totals
    {cost_dollars_per_hour, load_MW, generation_MW, reserve_MW}, most_loaded_lines
    {from, to, loading_pct} (top N), operating_margin_MW.
  criteria:
    standard: Every requested constraint and field is in that list (different top-N or file path is still standard).
    extra_outputs: Constraints are covered, but the report must carry fields the script does not write (e.g. LMPs, line flows in MW, binding lines, renamed keys).
    extra_constraints: The task adds modeling the script lacks (ramp limits, unit commitment, N-1 security, losses, AC flow, reserve zones, reserve costs).
  reconsider: A false "standard" silently drops a requirement. Re-read the task statement on any close call that leans standard.
matpower_branch_model:
  type: noul
  instructions: Does the task explicitly require transformer tap ratios or phase-shift angles in the DC model?
  criteria:
    true: The statement names tap ratios, phase shifters, or MATPOWER's makeBdc/rundcopf model as required.
    false: Plain "DC power flow/balance" wording, or no mention. This is the default.
  reconsider: A false true changes every line flow away from the standard b = 1/x model. Reconsider any close call that leans true.
```

### 3. Inspect (script)

```bash
python3 scripts/dispatch.py inspect /root/network.json
```

Prints JSON: bus, generator and branch counts (with online and in-service counts), whether bus numbers are contiguous, slack buses, total load, online Pmax/Pmin, reserve requirement and the maximum deliverable reserve, the gencost model mix, the counts of RATE_A=0, tap and phase-shift branches, any extra top-level keys, and `warnings`. A warning that says "infeasible" predicts a solve failure (step 5, exit 2). Unexpected `extra_keys` may carry data the task expects you to use: re-check `requirements_fit` against them.

### 4. Solve (script)

```bash
python3 scripts/dispatch.py solve /root/network.json --out /root/report.json --details /root/dispatch_details.json
```

Add `--top N` when the task asks for a different number of lines. Add `--branch-model matpower` only when `matpower_branch_model` is true. The script runs this model:

- DC approximation: lossless lines (r and line charging ignored), flat 1.0 pu voltages, small angles (sin θ ≈ θ). Flow depends only on angles and reactances. Bus shunts are ignored.
- Variables: Pg (MW) and Rg (MW) per generator, θ (rad) per bus.
- Minimize Σ cost_i(Pg_i) over online generators. For gencost model 2, `NCOST` coefficients are listed highest order first: c2·P² + c1·P + c0, or c1·P + c0, or a constant. P is in MW. Model 1 is piecewise linear over (P, C) breakpoints. Startup/shutdown costs are excluded.
- Nodal balance at each bus: Σ Pg at the bus − Pd = baseMVA · (B θ)_bus. B is built from in-service branches with b = 1/x (x = column 3). θ = 0 at the type-3 slack bus, with one reference per island.
- Pmin ≤ Pg ≤ Pmax; 0 ≤ Rg ≤ reserve_capacity; Pg + Rg ≤ Pmax; ΣRg ≥ reserve_requirement.
- |baseMVA · b · (θ_f − θ_t)| ≤ RATE_A (column 5) for lines with RATE_A > 0.
- Solver order: CLARABEL, then HiGHS (LP only), ECOS, SCS.

It then re-derives nodal mismatch, limits, reserve and line loading from the solution (`checks`) and writes the report:

```json
{
  "generator_dispatch": [{"id": 1, "bus": 316, "output_MW": 476.0, "reserve_MW": 8.28, "pmax_MW": 491.0}],
  "totals": {"cost_dollars_per_hour": 0.0, "load_MW": 0.0, "generation_MW": 0.0, "reserve_MW": 0.0},
  "most_loaded_lines": [{"from": 2198, "to": 1324, "loading_pct": 100.0}],
  "operating_margin_MW": 0.0
}
```

How the report fields are defined:
- `id` is the 1-based row in `gen`, and `bus` is the bus number, not the array index. Every generator row is listed. Out-of-service units are reported with 0 output and 0 reserve.
- Cost is Σ cost_i(Pg_i) in $/hr, including c0 of every online unit.
- `load_MW` is Σ Pd. `reserve_MW` is ΣRg.
- `loading_pct` is |flow_MW| / RATE_A · 100. Lines are ranked by loading rounded to 2 decimals, and ties keep branch-file order.
- `operating_margin_MW` is Σ(Pmax − Pg − Rg) over online units: the uncommitted headroom.
- Values are rounded to 2 decimals.

`--details` adds the solver, the LMPs ($/MWh, the dual of nodal balance), the binding lines, and every line's flow. Without congestion, each bus LMP equals the marginal unit's marginal cost, 2·c2·P + c1. Use it for `extra_outputs` and for the final summary.

### 5. Branch on the exit code (script result)

- **0**: solved and all checks pass. Continue.
- **2**: not solved. The JSON gives `status`, `solvers_tried`, and `feasible_without_line_limits`. If that is true, transmission limits make the case infeasible. If false, the cause is supply or reserve adequacy: compare the inspect warnings (load vs online Pmax, Pmin vs load, requirement vs deliverable reserve). Do not loosen constraints to force a report. State the infeasibility and its cause in step 7. Write a report only if the task statement says what to output in that case.
- **1**: an `ERROR:` line on stderr names one of three problems: a missing key, a reserve array whose length differs from `gen`, or an unsupported cost (polynomial above degree 2, negative c2). A failed bootstrap also exits 1. For unsupported data, treat the case as `extra_constraints` and extend a copy of the script.
- **3**: solved, but a check failed (look at the non-zero `checks` entries). Re-run once. If it still fails, report the violation and its size rather than hiding it.

### 6. Extend, then check (client task + script)

- `standard`: skip the extension.
- `extra_outputs`: add the requested fields to the report from `--details` data or the solve output. Do not change the solved numbers.
- `extra_constraints`: copy `scripts/dispatch.py` to a work directory. Add the constraints in `solve_problem`, next to the existing `cons += [...]`, and run the copy with the same command.

After any change to the report, and once anyway before delivering, run:

```bash
python3 scripts/dispatch.py check /root/network.json /root/report.json
```

It re-runs a DC power flow from the reported (rounded) dispatch and verifies limits, reserve, coupling, totals, cost, margin, and the top line. Exit 0 means `checks_pass: true`. Fix whatever is listed in `errors` and re-check until it passes. Use the same `--branch-model` as the solve.

### 7. Deliver (client task)

Confirm the report exists at the requested path with exactly the requested keys. Then reply briefly with: the total cost, load, generation and reserve against the requirement; the operating margin; the solver and its status; the top lines; and how many lines are binding (`lines_tied_at_top_loading`). Include any warnings or infeasibility explanation.

## Gotchas

- Bus numbers can be non-contiguous. Always map bus number → array index. Never use `bus - 1`. The scripts do this.
- MATPOWER columns are 0-indexed. bus: 0 number, 1 type (3 slack, 2 PV, 1 PQ), 2 Pd (MW). gen: 0 bus, 7 status, 8 Pmax, 9 Pmin. branch: 3 x (pu), 5 RATE_A (MVA, 0 = unlimited), 8 tap, 9 shift (degrees), 10 status. gencost: 0 model, 3 NCOST, 4+ coefficients.
- Per unit: P_pu = P_MW / baseMVA. Reserve data is already in MW.
- Reserve is free in this market, so any ΣRg ≥ requirement is optimal. The total can exceed the requirement slightly, and the per-unit split (and therefore the margin) is not unique. Generator outputs are not unique either when costs are linear. Cost, load and generation are unique. Do not post-process the reserves.
- Many lines often bind at exactly 100%. The top-3 list is then a deterministic pick among the tied lines. Mention the tie count instead of claiming those three are uniquely the worst.
- The default branch model ignores taps and phase shifts (b = 1/x), as the standard DC dispatch formulation does. Only switch models on an explicit requirement.
- Use CLARABEL. OSQP fails on these ill-conditioned DC-OPF-with-reserve problems.
