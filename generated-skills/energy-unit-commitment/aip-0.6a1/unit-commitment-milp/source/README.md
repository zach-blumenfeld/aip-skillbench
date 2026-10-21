# Source and provenance: unit-commitment-milp

## Provenance

Compiled into one AIP 0.6a1 skill from three curated Agent Skills, copied here verbatim:

- `milp-solver-workflow/SKILL.md`: MILP workflow: variable map, sparse rows, sign-safe encoding, piecewise costs, HiGHS via SciPy, extraction/validation, infeasibility debugging, repair LPs, reporting discipline.
- `unit-commitment-data-modeling/SKILL.md`: parsing structured UC data: concept-to-field mapping, data shapes, time/order/unit handling, production convention, startup tiers, cost curves, renewables, parser checks, common mistakes.
- `unit-commitment-operating-rules/SKILL.md`: UC operating rules: variables, feasibility checks, transitions, capacity, balance/reserve, reserve deliverability, ramping, min up/down, startup/production costs, workflow, pitfalls.

Target task: day-ahead UC on a pglib-uc / UnitCommitment.jl style `network.json` (RTS-GMLC:
48 h, 73 thermal, 81 renewable), run in a `python:3.12-slim` container that has only
numpy 1.26.4 and scipy 1.13.1 (HiGHS through `scipy.optimize.milp`). The report goes to
`/root/report.json` in the format the task statement gives.

## Procedure graph and component-kind choices

1. `inspect-case` (**execution**): parsing, alias mapping, normalization, and the parser
   checks are deterministic rules over structured data, so they are a script. This is the
   start step, so it declares every caller input (paths, task statement, solver limits).
2. `read-task-conventions` (**decision**): the sources say "follow the prompt" on three
   points that change the model: whether renewables may be curtailed, whether renewable
   headroom counts as reserve, and whether post-horizon min up/down obligations apply.
   Each is a yes/no judgment over the task text with an answer space fixed in advance, so
   a decision with three nouls and thresholds, not prose.
3. `solve-and-validate` (**execution**): building the MILP, solving, rounding checks, the
   fixed-commitment polish LP, conversion to actual MW, and independent validation are
   all code. It is one step because they share the in-memory model. The library
   (`scripts/uc_core.py`) is shared with the other two scripts so the parser, cost
   functions, and validator are defined once. HiGHS is a maintained solver, used through
   SciPy rather than writing our own.
4. `by-validity` (**router**): carries the source rule "write final output only after
   validation passes" as a branch.
5. `write-report` (**execution**): report construction, recomputing cost and summaries, and
   reading the file back are deterministic.
6. `diagnose-failure` (**client_task**): when there is no valid schedule the agent has to
   reason over the solver message and the failing checks, then rerun or fix the code. That
   output is free-form, so it is a client task, with the debugging checklist in
   `references/uc-formulation.md`.
7. `end`: `solve_summary` and `validation`, which exist on both branches.

Scripts: `scripts/uc_core.py` (library), `scripts/inspect_case.py`, `scripts/solve_uc.py`,
`scripts/write_report.py`. Asset: `assets/diagnose.md` (client-task template). Reference:
`references/uc-formulation.md` (field map, model rows mapped to report checks, costs,
solver statuses, debugging).

## Modeling decisions (and why)

- Internal output is above minimum (`pg`); reports, balance, and validation use actual MW
  (`pmin*u + pg`). This follows the sources' rule to choose one convention and convert at
  the edges.
- Joint production+reserve capacity uses the startup/shutdown capability (`ramp_startup_limit`,
  `ramp_shutdown_limit`). For units with min up = 1 it is split into two rows, because such a
  unit can start and stop in consecutive periods.
- Reserve is limited to `ramp_up_limit` and counts toward the ramp-up row. This is
  stricter than headroom alone, as the "reserve deliverability" section requires.
- Startup tiers: one binary selector per tier. Tier s is allowed only if there was a
  shutdown inside its offline-duration window. A pre-horizon shutdown is placed
  `time_down_t0` periods before period 1, and the coldest tier is always allowed. The
  validator recomputes cost with the source's rule (largest lag <= offline duration, else
  the first tier).
- Piecewise total-cost curves become segments filled from pmin. Cost at pmin is
  charged per online period, which is the source's "first point = minimum-output cost".
  Fill-order binaries are added only when a curve is non-convex.
- Min up/down windows are truncated at the horizon start, with initial obligations fixed
  from `time_up_t0`/`time_down_t0`. Post-horizon obligations are enforced only when the
  decision says the task requires it.
- After the MILP solve, binaries must be within 1e-4 of 0/1. They are then rounded and
  fixed, and the SAME model is re-solved as an LP (the source's "repair LP must include
  every family" rule).
- Experiments on the real case:
  - Keeping only `u` integer gave a worse incumbent (0.91% gap against 0.49% in 300 s).
    Making w and the tier selectors continuous (exact given integral u and v) gave 1.47%.
    So all transition binaries stay.
  - Plain HiGHS under a time limit varied from 0.49% to 2.03% gap between runs on scipy
    1.16, and reached 2.36% (1.2563M) on the container's scipy 1.13.1.
  - The phased search (LP relaxation; an LP-guided start that fixes LP-integral binaries;
    the full MILP for 25% of the budget for the bound; then time-window, RINS, and
    unit-group neighborhood sub-MILPs) reached 1.2333M at 0.64% in 300 s on scipy 1.13.1.
    With the default 420 s budget it reached 1.2321M at 0.44% and stopped at 357 s after a
    full neighborhood cycle with no improvement.
  - Ramp rows are tightened with v/w; they have the same integer points and a tighter LP.
- `solve-and-validate` sets `timeout: 900`, and the script caps the solve budget at 780 s.
  The default `aip run` script timeout (60 s) is too short for this MILP.

## Completeness check (source items -> where they live)

milp-solver-workflow:
- Workflow 1-10: steps 1-6 of the graph (`inspect-case` covers 1, `solve-and-validate`
  covers 2-9, the router plus `write-report` cover 10).
- Variable map / alloc pattern: `Model.alloc` in `uc_core.py`.
- Sparse constraint / add_row: `Model.add_row` with CSR assembly.
- Sign-safe encoding and the hand check: rows in `build_and_solve`; the hand check is in
  the reference.
- Match model rows to validation: the table in the reference; `validate()` has one
  check per family.
- Piecewise-linear cost conventions: `curve_on_range`, segments, reference "Costs".
- HiGHS via SciPy, time limit, gap, status, no-incumbent handling: `build_and_solve`,
  `status_label`, `reported_gap`.
- Extraction and validation bullets: fractionality check, actual-MW conversion,
  recomputed summaries/cost, validator reads only input plus arrays, "pass" only after
  validation (`write-report` re-validates).
- Debugging infeasibility (8 causes and the staged approach): reference "Debugging", used
  by `diagnose-failure`.
- Repair LPs and heuristics: the polish LP is the full model; reference and anti-patterns.
- Reporting discipline: deterministic ordering (input order), no placeholders, gap kept
  separate from feasibility, null gap when unknown, no trust in self-reported "pass".

unit-commitment-data-modeling:
- Parsing workflow 1-7 and "map concepts, not names" table: `ALIASES`/`GEN_ALIASES`,
  `load_case`, reference field-map table.
- Common data shapes (scalar, time series, curve/tier, nested objects): `_series`,
  `_as_named_list`, the tier and curve parsing.
- Time, ordering, and units: 0-based internal with 1-based report labels, source order
  kept, IDs opaque, length checks, thermal and renewable sets kept separate. Units are MW
  and hours as given; nothing is converted.
- Production convention: model and report conversion.
- Startup tiers (`choose_startup_tier`): `startup_cost`, `startup_windows`.
- Cost curves (`interpolate_total_cost`): `production_cost`.
- Renewables: bounds, fixed when min == max, curtailment and reserve set by the decision,
  zero cost.
- Parser-level validation and the "also check" list: `load_case` and `inspect_case.py`.
- Common mistakes: reference "Common mistakes" and anti-patterns.

unit-commitment-operating-rules:
- UC in one paragraph: `purpose`.
- Keep concepts separate (u, start, stop, p, r): variable list in the reference and the model.
- Core feasibility checks list: `validate()` (names once each, lengths, binary, offline
  zeroes, min/max, must-run, transitions, balance, renewable bounds, reserve,
  deliverability, min up/down plus initial, recomputed cost and summaries).
- Transition logic and its validation pattern: logic rows plus the validator.
- Capacity and offline zeroes; demand, renewables, and system reserve; reserve
  deliverability including startup reduction and the "analogous shutdown" rule: joint
  capacity rows with SU/SD, `r <= RU*u`, validator checks.
- Ramping with initial output, and reserve in ramp-up: ramp rows plus the validator
  (`initial_conditions` for period 1).
- Minimum up/down with pre-horizon time and the prompt's post-horizon choice: window rows,
  bound fixing, the `enforce_post_horizon` decision.
- Startup costs and production costs (no invented components): objective plus validator
  cost.
- Implementation workflow and common pitfalls: the graph order plus anti-patterns.

## Deliberate drops

- The sources' generic examples of other input formats (CSV, spreadsheets, databases):
  the alias layer accepts dict- or list-shaped JSON resources, and a schema it cannot map
  stops with the missing field and the available keys so the agent can extend the
  aliases. Writing loaders for formats this task type never ships would be speculative.
- Storage, imports/exports, zones, and network objects in the data-modeling concept list:
  the task excludes network modeling and the data has none. Recorded under
  `do_not_use_when`.
- The general "use for linear/piecewise objectives in any time-expanded scheduling"
  framing in milp-solver-workflow: this skill is scoped to UC. The general MILP practices
  are kept as they apply here.
