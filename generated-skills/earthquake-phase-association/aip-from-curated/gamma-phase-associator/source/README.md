# gamma-phase-associator — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill `gamma-phase-associator` (the
`aip-from-curated` track for the `earthquake-phase-association` task). The
canonical original is preserved verbatim at `source/ORIGINAL_SKILL.md`.

The `name:` frontmatter is unchanged (`gamma-phase-associator`) so the task's
mounted skill name matches.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md` (the
  GaMMA `association` and `estimate_eps` API documentation).
- `source/procedure.schema.json` — the AIP `procedure` schema (v0.3a2) the body
  validates against. Bundled locally so the skill is self-contained.
- `references/association-api.md`, `references/estimate-eps-api.md` — the
  source API tables, preserved faithfully for on-demand loading.
- `scripts/build_gamma_config.py` — authored config-builder (see below).

## Schema choice

`procedure` schema (reused, not drafted). The curated skill is pure API
*reference* for an external library, but the work it supports is a procedure:
prepare stations → prepare picks → build config → run `association` → build the
event catalog. That maps cleanly onto the procedure schema (script-backable
step nodes connected by inputs/outputs), so the conversion structures the API
knowledge as that execution graph and pushes the dense reference tables into
`references/` for progressive disclosure.

## Scope (faithful to the curated skill)

The curated skill documents the GaMMA core API (`association`, `estimate_eps`)
and the expected input/output formats; it bundles no tool of its own. This
conversion preserves that scope — it teaches the agent the GaMMA API and the
workflow for using it, rather than re-scoping into a one-shot task pipeline.
Phase *picking* (producing the picks) is explicitly out of scope (a picker's
job) and is called out in `do_not_use_when`.

## Script vs prose decisions

AIP best practice: steps containing if/then rules, numeric thresholds, or
lookup tables should be backed by a script unless the inputs aren't available
as structured data.

- **build-config → scripts/build_gamma_config.py (script).** This is the one
  block of genuinely scriptable, source-documented logic with structured
  inputs: the `method -> oversample_factor` rule (BGMM=5.0 / GMM=1.0, an
  explicit if-rule in the source config table), the numeric config defaults,
  the `bfgs_bounds` construction in the documented
  `((x_min,x_max), …, (None,None))` shape, the `use_amplitude -> max_sigma22`
  dependency, and validation (method, dims, bounds presence, eps presence). The
  script is stdlib-only and does **not** import `gamma` or `pandas`, so it runs
  and tests standalone. `dbscan_eps` is a parameter, not computed in-script, to
  avoid pulling in the `gamma` dependency — the agent estimates it via the
  library's `estimate_eps` (which I do not reimplement) or sets a manual value.
- **prepare-stations, prepare-picks (prose, the documented exception).** Their
  real inputs — the source CSV's column names, the projection origin, and the
  picker's output shape — are task-specific and unknown at authoring time, so
  they are not available as structured data. The non-obvious bits that *are*
  fixed (the required output columns, the `z(km) = -elevation/1000` convention,
  the per-id collapse idiom, the UTC/lowercase requirements) are stated inline
  with the exact pandas idiom quoted so the agent reproduces them consistently.
- **run-association, build-catalog (prose).** `association` is the external
  library call; output handling (back-projection to lon/lat, the ISO time
  column, optional assignment join) is task-shaped. Kept as prose referencing
  the return-value schema rather than over-restricting with a wrapper.

## Source-content classification (completeness check)

- "What is GaMMA?" (clustering, multivariate Gaussian, EM, source params) →
  **Mapped** to `purpose` and `references/association-api.md` header.
- Citation (Zhu et al. 2022) and "derivative of …/GaMMA" repo note → **Mapped**
  to the `references/association-api.md` header.
- "Installing GaMMA" pip command → **Mapped** to step `install-gamma` (command
  preserved verbatim, including the `wayneweiqiang/GaMMA.git` URL the source
  uses for install).
- `association` signature + purpose → **Mapped** to step `run-association` and
  `references/association-api.md`.
- Input parameters table (picks/stations/config/event_idx0/method) → **Mapped**
  to `references/association-api.md` and the `run-association` inputs.
- `picks` DataFrame columns + notes (UTC, lowercase type, amp 0/-1 filtering,
  index tracks identity) → **Mapped** to step `prepare-picks` and the
  reference.
- `stations` DataFrame columns + notes (projected coords, id match, per-id
  collapse rule) → **Mapped** to step `prepare-stations` and the reference (the
  collapse idiom is quoted in both).
- Config keys — required / velocity / DBSCAN / filtering / other tables →
  **Mapped** to `references/association-api.md`; the rules and defaults are
  additionally encoded in `scripts/build_gamma_config.py`.
- Return values — `events` (list[dict]) and `assignments` (list[tuple]) tables
  → **Mapped** to step `run-association` outputs, step `build-catalog`, and the
  reference.
- `estimate_eps` — signature, purpose, params, columns, return (seconds),
  example usage, practical notes (10-20 s typical; often hardcoded 10-15 s),
  related config → **Mapped** to `references/estimate-eps-api.md` and the
  `build-config` step description.

No deliberate drops: every distinct piece of source content is mapped into the
body, a reference file, or the config-builder script.

## Functional testing

See the parent conversation for the fresh-agent functional-test results.
