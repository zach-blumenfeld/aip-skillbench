# Source README — energy-market-counterfactual

## Provenance

Compiled from four curated Agent Skills bundled with the SkillsBench
`energy-market-pricing` task, plus the task's own `instruction.md`:

- `source/economic-dispatch/SKILL.md` — DC-OPF cost model, generator limits,
  reserve co-optimization (`Rg >= 0`, per-gen cap, capacity coupling
  `P + R <= PMAX`), system reserve requirement, dispatch/output formatting,
  solver choice (CLARABEL over OSQP).
- `source/economic-dispatch/references/cost-functions.md` — MATPOWER polynomial
  and piecewise-linear cost formats, typical coefficient ranges, marginal cost.
- `source/dc-power-flow/SKILL.md` — DC approximations, bus-number mapping,
  susceptance-matrix construction, nodal power balance
  `Pg - Pd == B[i, :] @ theta`, slack bus, line flows, loading %, per-line
  thermal constraints.
- `source/dc-power-flow/scripts/build_b_matrix.py` — reference implementation
  of the susceptance-matrix build and per-branch flow calculation. Its logic
  is reproduced in `scripts/_dcopf.py` (kept there rather than imported so a
  single self-contained script solves each scenario).
- `source/locational-marginal-prices/SKILL.md` — LMP extraction from balance
  duals (with `baseMVA` scaling), reserve MCP extraction, binding-line
  detection at ≥99% loading, negative-LMP interpretation, counterfactual
  analysis pattern (base → modify limit → resolve → compare).
- `source/power-flow-data/SKILL.md` — MATPOWER JSON schema, bus/gen/branch
  column layouts, per-unit system, reserve data fields, bus-number mapping,
  slack-bus finder, total-load computation, large-file handling caveat.
- `source/task/instruction.md` — the actual task prompt (regional market
  analyst; counterfactual on line 64→1501 at +20%) and the exact `report.json`
  output schema.

Upstream source lives under the SkillsBench monorepo:
`vendor/skillsbench/tasks/energy-market-pricing/environment/skills/`.
All files above are copied verbatim into `source/`; do not edit them in place —
edit the compiled AIP skill instead.

## Design

**One coherent procedure.** The four curated skills together describe a single
workflow: parse network → build DC-OPF with reserves → extract dual-based
prices → run a counterfactual on one line's thermal limit → report the impact.
That workflow is compiled into one AIP procedure with four steps.

**Start inputs, not hard-coded scenario.** The task's own scenario (line
64→1501, +20%) is baked into the instruction, but the compiled skill takes
`scenario_from_bus`, `scenario_to_bus`, and `scenario_delta_pct` as start
inputs so the same skill runs any single-line thermal-relaxation study.

### Step-kind choices

Every step is `execution`. Justification against the AIP Best Practices order
(script → decision → client_task):

- **`solve-base`** (execution). The logic is a deterministic convex QP over
  structured inputs — numeric calculation with fixed constraints. A script is
  strictly correct; a decision cannot pick a dual value and a client_task
  would ask the agent to hand-roll the solver.
- **`solve-counterfactual`** (execution). Same solver applied to a network
  whose target branch's `RATE_A` is scaled by `1 + delta_pct/100`. The
  line-lookup is a deterministic table search (match either orientation), and
  the resolve is the same convex QP. Script.
- **`compute-impact`** (execution). Cost subtraction, per-bus delta
  computation, deterministic top-3 sort by ascending delta, and a set-difference
  test for `congestion_relieved`. All lookup/arithmetic — no judgment. Script.
- **`end`** — terminal shape declaration.

No `decision` or `client_task` steps: nothing in this pipeline requires
judgment or generation.

### Script layout

- `scripts/_dcopf.py` — shared helpers (dependency bootstrap, network load,
  branch mutation, the DC-OPF-with-reserves solver). Not referenced by any
  step; imported by the driver scripts alongside it.
- `scripts/solve_base.py` — driver for `solve-base` (stdin JSON → stdout JSON).
- `scripts/solve_counterfactual.py` — driver for `solve-counterfactual`.
- `scripts/compute_impact.py` — driver for `compute-impact`; also writes
  `report.json` at `output_path`.

The Ubuntu 24.04 container only ships `python3` / `pip`. Each driver calls
`_dcopf.bootstrap()` first, which pip-installs the pinned `numpy 1.26.4`,
`scipy 1.11.4`, `cvxpy 1.4.2` stack (matches the task's own `solve.sh`).

## Deliberate drops

Only content the AIP body doesn't carry (and doesn't need to). Everything else
from the source is embedded in `scripts/_dcopf.py`, in the driver scripts, in
the step descriptions, or in the anti-patterns.

- **Piecewise-linear cost format** (`cost-functions.md`, MATPOWER type-1
  gencost). The compiled solver handles polynomial type-2 with variable
  `NCOST` (quadratic, linear, constant). The task's network is uniformly
  type-2 quadratic; adding piecewise-linear would be dead code for this task
  and the wider counterfactual pattern.
- **Dispatch output & totals block** (`economic-dispatch` §Dispatch Output
  Format / Totals). The task's `report.json` schema does not include a
  per-generator dispatch list, total generation, total load, or operating
  margin. The solver still enforces all the corresponding constraints; only
  the report-time formatting is omitted.
- **Operating-margin formula** (`economic-dispatch` §Operating Margin). Same
  reason — not in the report schema. The primal `Pg` / `Rg` values remain
  available inside the solver call for anyone who wants to add them.
- **Piecewise-linear cost typical-values table** (`cost-functions.md`
  §Typical Values). Reference material for humans authoring test networks;
  the solver reads coefficients from `gencost`, so the table has no runtime
  effect.
- **Marginal-cost formula** (`cost-functions.md` §Marginal Cost). Not needed
  for solve or report — LMPs come from constraint duals, not analytic marginal
  costs.
- **`get_generators_at_bus` / `get_branch_info` helpers** (`power-flow-data`).
  The solver builds the bus-index map inline and iterates branches/generators
  directly; the wrapper helpers add no value here.
- **Bus-type table (Slack / PV / PQ)** (`power-flow-data`). Only the slack-bus
  identification (`type == 3`) is used; the PV/PQ distinction has no effect
  under DC-OPF (voltages are flat, reactive power ignored). The slack lookup
  is done in `_dcopf.solve_dcopf_with_reserves`.
- **`wc -l` / `du -h` quick file-size check** (`power-flow-data` §Handling
  Large Network Files). Anti-pattern advice — the equivalent "never read the
  file line-by-line, use json.load" rule is preserved in the anti-patterns
  list on the compiled skill.
- **Standalone `if __name__ == '__main__'` demo in `build_b_matrix.py`**.
  The library functions themselves are reproduced in `scripts/_dcopf.py`;
  the CLI demo entry point is not part of the runtime procedure.
- **DC approximation exposition** (`dc-power-flow` §DC Approximations —
  lossless lines, flat voltage, small angles). Background rationale for the
  linearization the solver already implements. The formulation itself
  (susceptance matrix, nodal `Pg - Pd == B[i,:]@theta`, `theta[slack]==0`,
  linear line-flow limits) is present in `_dcopf.py`; the narrative is not.
- **`total_load` helper** (`power-flow-data`). The solver uses per-bus loads
  in the nodal balance constraint, not an aggregate system load, so no total
  needs to be computed. If a caller wants system load for reporting, they can
  read it from the returned dispatch — but the report schema doesn't include
  it.
- **Economic intuition callouts** (`locational-marginal-prices` §Counterfactual
  Analysis §Economic Intuition — "relaxing a binding constraint cannot
  increase cost", "cost reduction quantifies the shadow price", "LMP
  convergence indicates reduced separation"). Interpretive commentary aimed
  at humans. The runtime enforces this by construction (CLARABEL will only
  report a lower or equal optimal cost for a strict constraint relaxation);
  the test `test_cost_reduction_non_negative` guards against sign errors.
- **Piecewise-linear cost example numbers** (`cost-functions.md` §Piecewise
  Linear §Example). Illustration for a format this solver does not consume;
  see the type-1 deliberate drop above.

Rules, thresholds, formulas, sign conventions, unit conversions, solver
choice, bus-mapping requirement, dual-scaling, negative-LMP interpretation,
binding-line threshold (99%), reserve-modeling constraints, and the
report-schema layout are all preserved in the compiled skill (either in
`scripts/_dcopf.py` or the SKILL.md anti-patterns).
