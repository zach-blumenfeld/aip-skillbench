# unit-commitment-milp — provenance and compilation notes

## Sources (copied verbatim in this folder)

| Path | Role |
| --- | --- |
| `milp-solver-workflow/SKILL.md` | MILP build/solve/extract/validate workflow, variable-map and sparse-row patterns, sign-safe encoding, HiGHS via SciPy, debugging infeasibility, repair-LP and reporting discipline |
| `unit-commitment-data-modeling/SKILL.md` | Mapping structured UC data to concepts, time/order/unit rules, production convention, startup tiers, total-cost curves, renewables, parser-level checks |
| `unit-commitment-operating-rules/SKILL.md` | UC feasibility families: transitions, capacity/offline zeroes, balance, reserve deliverability (startup/shutdown capability, ramp), min up/down with initial history, startup and production costs, pitfalls |

These three curated skills describe one workflow (parse UC data → formulate → solve with an open-source
MILP solver → validate independently → report). They were compiled into one procedure graph.

Environment facts used: the task container is `python:3.12-slim` with only `numpy==1.26.4` and
`scipy==1.13.1` (HiGHS through `scipy.optimize.milp`); the input file is `network.json` (90,531 bytes,
full size, single-line JSON) in pglib-uc / UnitCommitment.jl format: `time_periods` (48), `demand`,
`reserves`, 73 `thermal_generators` keyed by name (16 fields each: must_run, power_output_minimum/maximum,
ramp_up/down_limit, ramp_startup/shutdown_limit, time_up/down_minimum, power_output_t0, unit_on_t0,
time_up_t0, time_down_t0, startup tiers [{lag, cost}] (1–3 tiers), piecewise_production [{mw, cost}]
total-cost points from pmin to pmax), and 81 `renewable_generators` with per-period min/max (most periods
min == max, some curtailable). The scripts read this schema exactly and preserve source order; nothing
about the expected answer is hardcoded.

## Graph and step-kind choices

| Step | Kind | Why |
| --- | --- | --- |
| `inspect-data` (start) | execution | Parser-level checks (lengths, finiteness, pmin<=pmax, renewable min<=max, curve points, repeated MW points, tiers, repeated/unsorted lags, duplicate IDs, initial status/output consistency, capacity adequacy, convexity) are deterministic rules. |
| `data-ok` | router | Branch on the script's `data_ready`. |
| `normalize-data` | client_task | Mapping an unfamiliar schema "by meaning, not names" needs judgment and produces a new file (generation). Carries the data-modeling concept table, cost-curve/tier/unit conventions. Loops back to `inspect-data` so normalized data is re-checked. |
| `conventions` | decision | Four yes/no judgments over the prompt that change the formulation (post-horizon min up/down, renewable reserve, no curtailment, shutdown capability). Answer space is fixed, so a decision, not free text; thresholds flag close calls. |
| `solve` | execution | The whole formulation is deterministic code: sparse MILP, HiGHS (maintained solver, not re-implemented), near-integral rounding guard, conversion to actual MW. |
| `solved` | router | No incumbent / infeasible / non-integral / data error → debug; incumbent → validate. |
| `validate` | execution | Independent re-derivation of every feasibility family and the cost from arrays + input only (the source's "match model rows to validation" checklist). |
| `valid` | router | Only a validated schedule is reported. |
| `debug` | client_task | Diagnosing infeasibility/encoding bugs needs reasoning; the template carries the source's debugging lists; loops back to `solve` so every fix is re-solved and re-validated. |
| `write-report` | client_task | The report schema is task-specific and unknown in advance; the agent writes it from the validated solution file with a script. |
| `report-check` | decision + router | Yes/no gate on schema conformance; loops back to `write-report` if not. |

Formulation choice: the pglib-uc reference formulation (output above minimum; joint production+reserve
capability with startup and shutdown capability terms; ramp-up on production+reserve and ramp-down on
above-minimum output from `power_output_t0`; turn-on/turn-off min up/down windows truncated at the
horizon end; initial obligations from `time_up_t0`/`time_down_t0`; startup tiers by prior offline
duration; total-cost piecewise segments). Startup and shutdown capability rows are merged when min up >= 2
(valid because start-then-stop in consecutive periods is impossible), which tightens the LP. Measured:
on the real 73-unit case the container HiGHS reaches a 1% gap in ~10 s; tighter gaps hit the time
limit with a better incumbent, hence defaults of `mip_rel_gap` 0.001 and `time_limit_s` 300 when the task
gives none. Validator cost recomputation matched the solver objective to 1e-9 in tests.

Scripts: `uc_common.py` (shared loader, checks, curve interpolation, tier rule, offline durations),
`inspect_data.py`, `solve_uc.py`, `validate_uc.py`. Three entry scripts because they are independent
stages that the graph re-enters separately (re-inspect after normalization, re-solve after debug,
validate after any solve).

## Completeness map (where each source item lives)

- MILP workflow steps 1–10 → `inspect-data`, `solve`, `validate`, `write-report` steps; variable-map,
  sparse-row, sign-safe encoding, hand test, family-by-family → `solve_uc.py` and `references/uc-model.md`.
- Model-row ↔ validation checklist → `references/uc-model.md` table; `validate_uc.py` check families.
- Piecewise conventions → `assets/normalize.md` §5, `references/uc-model.md`, `solve_uc.py` segments
  (ordering binaries added for non-convex curves).
- Solver use, status, incumbent, gap/bound → `solve_uc.py` (`solve_status`, `solve_info`), routers.
- Extraction/validation bullets, "pass only after validation" → `solve_uc.py` rounding guard,
  `validate_uc.py`, `assets/write_report.md`, anti-patterns.
- Debugging infeasibility, staged debugging, repair LPs → `assets/debug.md`, `references/uc-model.md`,
  anti-patterns.
- Reporting discipline → `assets/write_report.md`, `report-check`.
- Data parsing workflow, concept table, data shapes, time/order/units, production convention, startup
  tiers, cost curves, renewables, parser checks, common mistakes → `assets/normalize.md`,
  `uc_common.py`, `inspect_data.py`, `conventions` decision, anti-patterns.
- Operating rules: concepts, core feasibility list, transitions, capacity, balance/renewables/reserve,
  deliverability (startup/shutdown), ramping, min up/down, startup and production costs, workflow,
  pitfalls → `solve_uc.py` rows, `validate_uc.py` families, `conventions`, anti-patterns.

## Deliberate drops

| Source item | Reason |
| --- | --- |
| "This is a workflow and implementation guide, not a complete formulation" (milp-solver-workflow, operating-rules) | Superseded: the compiled skill ships a complete formulation in scripts. |
| "UC in one paragraph" background prose | Background; condensed into `purpose`. |
| Example Python snippets (alloc, add_row, choose_startup_tier, interpolate_total_cost, validation asserts, transition/ramp/min-up loops) as text | Implemented as working code in `scripts/` rather than repeated as prose. |
| The suggested in-memory `case = {...}` normalized dict layout | Replaced by the canonical pglib-uc schema the scripts read; same content (periods, ordered names, demand, reserve, thermal params, renewable min/max). |
| Generic list of possible sources (spreadsheets, databases) beyond the parse instruction | Kept as one line in `assets/normalize.md` step 1; no further detail needed. |
| "Use helper functions or dictionaries" style advice | Embodied by the `Model.alloc/add_row` helpers. |
| "A fixed-commitment repair LP is useful if ..." as an available step | No repair-LP step is shipped; the debug loop re-solves the full model (which always carries every family). The warning itself is kept in `assets/debug.md` and anti-patterns. |

## Functional test log

- `aip run` on a synthesized full-length network.json (same schema, single-line JSON, perturbed values):
  inspect → conventions → solve → validate → write-report → report-check (false, then true) → end;
  all 16 validator checks pass, recomputed cost equals the solver objective.
- Second run on a renamed-key variant of the file: normalize-data branch → inspect (ready) → solve with a
  1 s limit → `no_incumbent` → debug (raise limit) → solve → validate → report → end; same objective as
  run 1, confirming the normalization.
- Validator fault injection (extra MW, offline-with-output, objective tamper, reserve cut, reordered IDs)
  fails the expected check families.
- Container-equivalent environment (Python 3.12, numpy 1.26.4, scipy 1.13.1 / HiGHS) on the real file:
  1% gap in ~10 s, validated.
- Two fresh agents (CSV+summary report on the real file; JSON report with a no-curtailment rule) completed
  with validated outputs. Fixes made from their feedback: solution-file layout described correctly
  (name-keyed objects of per-period lists); inspect-data now flags periods where renewable max plus forced
  thermal minimum exceeds demand (no-curtailment infeasible) and errors on unavoidable over-generation;
  debug guidance for task rules that conflict with the data (prove, relax minimally, disclose); multi-file
  `report_path`; wall-clock headroom; rounding and status/gap disclosure guidance.
