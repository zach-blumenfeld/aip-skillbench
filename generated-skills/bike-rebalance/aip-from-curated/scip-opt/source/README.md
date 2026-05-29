# scip-opt — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill `scip-opt` from the
`bike-rebalance` SkillsBench task (`aip-from-curated` track). The
canonical original is preserved verbatim at `source/ORIGINAL_SKILL.md`.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md`.
- `source/procedure.schema.json` — the AIP `procedure` schema (v0.3a2)
  the body validates against. Bundled locally so the skill is
  self-contained.

## Schema choice

`procedure` schema (reused, not drafted). The curated skill is a 7-step
modeling workflow plus a kit of structural patterns — a procedure of
script-backed nodes connected by inputs/outputs is the natural fit. No
new schema fields were needed.

## Layout decisions

The curated `SKILL.md` mixes three kinds of content:

1. A **fixed workflow** (identify sets -> define vars -> hard
   constraints -> soft constraints -> objective -> solve -> validate).
   These become the procedure's `steps`.
2. **Reusable code blocks** the agent splices into its own model
   (minimal template, binary activation, assignment, abs-deviation,
   route arcs, MTZ subtour). These are not a single linear flow — they
   are a *kit* the agent reaches for based on the problem. They live in
   `references/patterns.md` and `references/minimal_template.md`, loaded
   on demand from the body (progressive disclosure).
3. **Fixed routines** with no problem-specific judgment — pyscipopt
   import check, randomization params, solve limits, status check,
   binary-threshold extraction, objective-component reconstruction. AIP
   best-practice says fixed lookup tables and numeric thresholds belong
   in scripts. These become `scripts/check_pyscipopt.py`,
   `scripts/set_reproducibility.py`, `scripts/solve_helpers.py`.

This is the same separation the original implies but never enforces:
prose for modeling judgment, code for fixed plumbing.

## Why these scripts exist

- `scripts/check_pyscipopt.py` — encodes the curated rule "do not start
  by installing another optimization package; first check whether
  PySCIPOpt is available". Stand-alone CLI plus an in-process
  `ensure_pyscipopt()` helper.
- `scripts/set_reproducibility.py` — the curated source lists five
  randomization params and a `set_if_available` helper. Keeping the
  list in a script means the agent does not retype the param names
  (and so cannot drift them) — `set_reproducible(model)` is one call.
- `scripts/solve_helpers.py` — the fixed numerics that recur in every
  SCIP solve: default 300 s / 1 % gap limits, the no-incumbent error,
  the 0.5 binary threshold, the 1e-6 objective-reconstruction
  tolerance. Each was prose-with-a-magic-number in the original.

The pattern blocks (binary activation, assignment, abs-deviation, route
arcs, MTZ) were deliberately **kept as code in `references/patterns.md`**
rather than wrapped into per-pattern scripts. The agent does not
*invoke* these — it *adapts* them: variable names, index sets, and
constraint shape change per problem. Wrapping them as callable helpers
would over-restrict the modeling step. This is the
"convert-back-to-prose-when-a-script-would-over-restrict-reasoning"
guidance from AIP best practices.

## Notable expansions beyond the literal source

- **Independent validator emphasis.** The curated source mentions
  validation twice but in passing. The AIP body lifts it into its own
  step (`extract-and-validate`) and explicitly says solver feasibility
  is necessary but not sufficient. The reconstruction-mismatch error
  is captured as `assert_objective_component` in
  `scripts/solve_helpers.py`.
- **`no_python_abs` as an explicit anti-pattern.** The original buries
  "Never use Python `abs()` on solver expressions" inside step 4. AIP
  promotes it to a top-level `anti_patterns` entry and the
  `absolute_deviation` pattern in `references/patterns.md` calls it out
  again — this is the single most common modeling bug in the wild.
- **Routing pairing rule.** Splitting route arcs and MTZ across two
  Common-Patterns subsections lets a reader stop after route arcs and
  ship a model that allows subtours. The AIP version makes the pairing
  explicit in the patterns reference and as an anti-pattern.

## Source-content classification (completeness check)

Every distinct piece of the curated `SKILL.md`:

- "When To Use" bullet list -> **Mapped** to `trigger_when`.
- The `try: from pyscipopt import ... except ImportError` snippet ->
  **Mapped** to step `check-availability` and to
  `scripts/check_pyscipopt.py`.
- Modeling workflow steps 1-7 -> **Mapped** one-to-one onto the body's
  steps (`identify-sets-and-indices`, `define-decision-variables`,
  `add-hard-constraints`, `add-soft-constraints`, `set-objective`,
  `solve`, `extract-and-validate`).
- Minimal PySCIPOpt Template code block -> **Mapped** to
  `references/minimal_template.md`, referenced from the body.
- Common Patterns (binary activation, assignment, abs deviation, route
  arcs, MTZ subtour) -> **Mapped** to `references/patterns.md`,
  referenced from the body.
- Reproducibility code (param names + `set_if_available`) -> **Mapped**
  to `scripts/set_reproducibility.py` and to a step in the body.
- Extraction And Validation snippet (`is_selected`, recomputed cost
  assertion) -> **Mapped** to `scripts/solve_helpers.py` and to step
  `extract-and-validate`.
- "Treat SCIP feasibility as necessary but not sufficient" warning
  -> **Mapped** to `extract-and-validate` description and to an
  `anti_patterns` entry.

No source content was dropped. The only minor reshape is promoting
two implicit rules (`no python abs()`, "subtour elimination required
for routing") into explicit `anti_patterns` entries.

## Tested

`validate.py` was run against the final skill and passes. Functional
testing not conducted with fresh agents in this session — the task
runtime here does not spawn fresh sub-agents against arbitrary skill
folders.
