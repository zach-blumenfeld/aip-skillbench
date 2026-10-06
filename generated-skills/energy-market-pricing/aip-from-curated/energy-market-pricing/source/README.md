# Source materials & authoring log — energy-market-pricing

## Provenance

Compiled from four curated freeform Agent Skills copied verbatim under
`source/` here:

- `source/power-flow-data/SKILL.md` — MATPOWER network.json parsing, per-unit
  conversions, bus-number mapping, slack-bus detection, reserve data.
- `source/dc-power-flow/SKILL.md` and `source/dc-power-flow/scripts/build_b_matrix.py` —
  DC power-flow approximations, susceptance matrix, line-flow and loading-pct
  calculation, line-flow limit constraints.
- `source/economic-dispatch/SKILL.md` and `source/economic-dispatch/references/cost-functions.md` —
  generator cost polynomials (variable NCOST), dispatch LP/QP formulation,
  reserve co-optimization, operating-margin calculation, CLARABEL solver choice.
- `source/locational-marginal-prices/SKILL.md` — extracting LMPs from
  nodal-balance duals, reserve MCP from reserve-requirement dual, binding-line
  identification (≥99% loading), counterfactual methodology (relax binding line,
  compare costs & LMPs).

`source/Dockerfile` captures the task container (Ubuntu 24.04 + python3 +
network.json). The container has only python3 + pip; the skill's scripts
pull in numpy and cvxpy from pip at install / first run.

The four source skills describe one coherent workflow: given a MATPOWER
network, clear a day-ahead-style energy market (dispatch + reserves + LMPs)
and, when the system is congested, quantify the shadow price of the most
binding line. The compiled skill expresses that as a single procedure graph.

## Step-kind choices

- **`solve_base` (execution).** Pure deterministic numerics: load JSON, build
  B, formulate and solve the DC-OPF with reserves, extract duals. Nothing
  here needs client judgment — it is a scripted calculation that must be
  exactly reproducible from the same network.json. Written as one script
  (`scripts/solve_base.py`) backed by a shared helper (`scripts/_dcopf.py`)
  that `solve_counterfactual.py` also imports — both solves must share
  identical formulations so the counterfactual difference is only the
  relaxed branch rating.

- **`evaluate_counterfactual` (decision, noul).** The question "is a
  counterfactual meaningful here?" is one yes/no judgment the client has
  genuine latitude over — it depends both on `binding_lines` (deterministic)
  and on whether the task-level request asked for congestion impact or
  base-case prices only. A noul with a `thresholds` entry (0.3, biased
  toward running the counterfactual when in doubt) keeps the client
  honest without over-restricting.

- **`route_counterfactual` (router).** Mechanical branch on the decision's
  `run_counterfactual` value. `true` goes to the counterfactual solve;
  `false` goes straight to the report.

- **`solve_counterfactual` (execution).** Target-line selection (highest
  loading%), scaling, re-solve, and impact math are all deterministic over
  the base-case results. No client judgment is needed to pick which
  binding line to relax — "most congested" is the maximally-informative
  choice. Script-encoded.

- **`write_report` (client_task).** The report is prose + markdown tables
  that synthesize across structured results. The agent's generation step is
  what produces the readable artifact; a template guides the sections and
  the sorting/filtering rules so the output stays consistent while leaving
  prose quality to the model.

- **`end`.** Declares the required final-state shape (`base_results`,
  `report`). Counterfactual keys flow through only when the counterfactual
  branch ran; they are not required at `end` because the base-only branch
  must also reach it.

## Corrections applied to source material (not drops)

- **LMP scaling.** `source/locational-marginal-prices/SKILL.md` scales the
  balance-constraint dual as `dual_val * baseMVA`. The constraint is written
  in per-unit, so the dual's units are $/hr-per-pu, i.e. $/hr-per-100-MW;
  the correct $/MWh conversion is `dual_val / baseMVA`. The source formula
  produces values 10,000× too large. Scripts and the DC-OPF reference apply
  the correct division; the SKILL anti-patterns list flags the multiplication
  as a trap.
- **Balance-constraint orientation.** The source writes `pg - pd == B@θ`.
  CVXPY's equality-dual sign convention gives the opposite-sign dual
  depending on which side is LHS. The compiled scripts write
  `B@θ == pg - pd` so that `dual / baseMVA` yields the correct LMP sign
  (positive at expensive buses, lowest at cheap-and-congested buses).
  Flagged in `references/dcopf-formulation.md`.
- **Tiny quadratic regularization.** `1e-4 * Σ (Pg_MW)²` added to the
  objective. For PGLib cases with real c2 > 0 this is dominated by the
  actual quadratic cost (cost perturbation < 0.01%); for pure-LP cases
  (c2 = 0) it eliminates vertex degeneracy that would otherwise give
  unstable or non-economic duals. The economic-dispatch source assumes
  quadratic costs and gives no guidance for the LP-degenerate case.

## Deliberate drops (recorded with rationale)

Every source item was walked line-by-line against the compiled
`SKILL.md`, scripts, references, and template. All rules, formulas,
lookups, and branching logic from the sources are carried forward in
code or references. The items below were intentionally not re-stated in
the compiled skill:

- **Freeform cost-function marketing table from `economic-dispatch`
  (typical values for Nuclear/Coal/Gas CCGT/Gas Peaker).** Not actionable
  during the solve — the scripts read whatever coefficients `gencost`
  provides. Preserved in `references/matpower-format.md` for a reader who
  wants a sanity-check range when debugging an unexpected dispatch, but
  not required for the procedure.
- **`cost-functions.md` piecewise-linear (MODEL=1) section.** The PGLib
  cases in this benchmark are all MODEL=2 polynomial, and the shared
  helper's `_gen_cost_term` only handles polynomial costs. If a future
  case needs piecewise-linear, this is an erroneous drop and the helper
  will need a code branch; today it is deliberate because adding
  untested MODEL=1 handling would introduce latent bugs.
- **Line-count / `wc -l` / `du -h` quick-check tips from
  `power-flow-data`.** Operator-only diagnostic noise; irrelevant to the
  autonomous procedure.
- **The `get_generators_at_bus` free-standing helper and the
  `get_branch_info` dict builder from `power-flow-data`.** Both are
  pedagogical sketches; the equivalent per-row loops are inlined in
  `_dcopf.py` and more direct for the problem's scale.
- **The DC-approximation rationale list (lossless, flat V, small angles)
  from `dc-power-flow`.** Kept in `references/dcopf-formulation.md`;
  the solver code implements them without needing the client to recite
  them each run.
- **The sign-convention tutorial on negative LMPs from
  `locational-marginal-prices`.** Collapsed into one line in the
  anti-patterns list and in `references/dcopf-formulation.md`; the
  procedure does not branch on sign, so it is reference-only material.
- **The abstract "step-by-step counterfactual methodology" prose from
  `locational-marginal-prices`.** The methodology is now operationalized
  in `scripts/solve_counterfactual.py`; the prose would be redundant.
- **The "economic intuition" callouts (relaxing a binding constraint
  cannot increase cost; shadow price interpretation).** Mentioned once
  as a one-liner the client includes in the report; it is not a
  procedure rule, only a framing for the reader.
