# Source and provenance

Compiled from three curated Agent Skills, copied verbatim here:

- `milp-solver-workflow/SKILL.md` — MILP workflow: variable map, sparse rows, sign-safe encoding,
  model↔validation matching, piecewise costs, HiGHS via SciPy, extraction, infeasibility debugging,
  repair LPs, reporting discipline.
- `unit-commitment-data-modeling/SKILL.md` — mapping structured UC data to concepts, time/order/unit
  handling, production convention, startup tiers, cost curves, renewables, parser-level checks.
- `unit-commitment-operating-rules/SKILL.md` — UC operating rules: transitions, capacity/offline zeroes,
  balance, renewables, reserve deliverability, ramping, min up/down, startup/production costs,
  validation, pitfalls.

Target task (functional-tested): day-ahead UC on a pglib-uc style `network.json`
(48 periods, 73 thermal, 81 renewable units), report JSON with fixed schema, container
`python:3.12-slim` + numpy 1.26.4 + scipy 1.13.1 (HiGHS). The sources are generic guides; the
skill turns them into one executable formulation + validator for that data shape, with a
converter branch for other schemas.

## Component kinds

| Component | Kind | Why |
| --- | --- | --- |
| Environment check | client step (one command) | trivial import check |
| Step 1 task-statement reading (`hour_label_start`, `production_convention`, `renewable_curtailment`) | decision | Conventions live in free prompt text; the answer space is fixed and each answer maps to a script flag. |
| Step 2 `inspect` | execution | Schema detection and parser checks (lengths, finiteness, pmin≤pmax, renewable min≤max, curve span, duplicate IDs/lags, t0 consistency, convexity) are deterministic rules. |
| Step 2 converter for a non-canonical schema | client_task | Field mapping for an unknown schema has to be written as code by the agent; `references/data-format.md` supplies the concept map and conversion rules. |
| Step 3 `solve` | execution | Formulation, solve, extraction, rounding, unit conversion, cost recomputation, validation and report writing are all deterministic code; scripting them removes the sign/index/convention bugs the sources warn about. |
| Step 4 `solve_action` | decision | Accept / rerun / debug depends on status + gap (rule-like) and the agent's unknown remaining time budget (judgment), so a typed choice. |
| Debugging after a FAIL | client_task (guided by `references/formulation.md`) | Diagnosing an unexpected infeasibility or a prompt rule the model lacks needs reasoning and code changes. |
| Step 5 `validate` | execution | Independent re-check reading only input + report. |

One script file (`scripts/uc_milp.py`) with three subcommands: the parser, model, and validator
share cost/tier/transition helpers, so splitting them would duplicate logic.

## Design choices beyond the sources

- Formulation follows the pglib-uc reference model (Knueven/Ostrowski/Watson style): above-minimum
  dispatch, combined startup/shutdown capability rows for UT>1 and separate rows for UT=1, reserve
  inside ramp-up, startup-tier allowance rows keyed on offline duration, t0 rows for ramp and
  shutdown. This is the "joint production-plus-reserve" + "startup reduction" pattern of the
  operating-rules source made complete.
- Production cost uses incremental segments of the total-cost curve (exact for convex curves; ordered
  binaries are added automatically for nonconvex ones), so the source's "identify the curve convention"
  is resolved by `references/data-format.md` (pglib curves are total cost at breakpoints).
- Default `mip_rel_gap` 1e-3, time limit 300 s. On the reference case HiGHS reaches a ~0.35% gap by
  4 min, and 600 s improved cost by only 0.003% (bound-limited), so 300 s balances economy against an
  unknown runtime budget. The decision in Step 4 handles slower instances.
- `--diagnose` (priced balance/reserve slacks) turns the sources' "add diagnostic slack variables,
  print largest violations" debugging advice into a script mode instead of prose.
- Report `objective_cost` = cost recomputed from arrays, cross-checked against the solver objective.

## Deliberate-drop log

| Source item | Reason |
| --- | --- |
| milp: generic `alloc`/`add_row` code snippets, SciPy call snippet | Implemented inside `scripts/uc_milp.py` (Model.var/Model.row, milp call); agent need not rewrite them. |
| milp: "useful for time-expanded scheduling models" framing; "not a complete formulation" disclaimers (all three) | Background; the compiled skill *is* a complete formulation. |
| ops: "UC in one paragraph" | Background the agent knows; key consequence (time coupling) is embodied in the model. |
| data: "Load data with structured parsers: CSV/sheets/databases" | Only relevant in the converter branch; covered by the concept map in `references/data-format.md`. |
| data: example `case = {...}` normalization dict | Replaced by `load_case()` and the canonical schema. |
| data/ops: `choose_startup_tier`, `interpolate_total_cost` code | Implemented as `startup_tier_cost`, `curve_cost` in the script. |
| ops: "Follow the prompt on whether post-horizon obligations are enforced" | Windows are clipped at T (in-horizon obligations enforced, nothing beyond T is representable in the report); noted in `references/formulation.md`. The infeasibility checklist keeps "enforcing post-horizon obligations the prompt excludes". |
| ops: "Apply analogous shutdown-period or pre-shutdown capability rules when data and prompt require them" | Not dropped: implemented as the `w[t+1]` reduction and t0 shutdown row. |
| milp: "Use deterministic ordering and plain numeric values / no placeholder values" | Enforced by the script (source order, floats/ints, all fields computed). |

Everything else (all rules, checks, pitfalls, conventions) is in `SKILL.md`, the script, or the two
references.
