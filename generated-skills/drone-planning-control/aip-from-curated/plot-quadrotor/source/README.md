# plot-quadrotor — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill `plot-quadrotor` from the
`drone-planning-control` SkillsBench task (`aip-from-curated` track).
The canonical original is preserved verbatim at
`source/ORIGINAL_SKILL.md`.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md`.
- `source/procedure.schema.json` — the AIP `procedure` schema (v0.3a2)
  the body validates against. Bundled locally so the skill is
  self-contained.
- Cross-referenced (for context only, not bundled):
  - the task `instruction.md` (which fixes the `plots/` directory
    location under `/root/results/<label>/`),
  - `environment/system_params.yaml` (source of `sample_rate`),
  - sibling skills (`motor-model-dynamics`,
    `position-controller-trajectory-planner`, `stepinfo-3d`),
  - the oracle `solution/solve.sh` (which inlines an equivalent
    `plot_quadrotor.py` and confirms the contract — five groups in
    Position/Orientation/Velocity/AngVel/Accel order, `figsize=(16,
    20)`, `dpi=100`, three named PNGs, blue desired vs red actual,
    `time_step * cumsum(|error|)`).

## Schema choice

`procedure` schema (reused, not drafted). Plotting is a deterministic
execution graph: load `time_step` -> slice into five groups -> render
each figure -> save and close. Exactly what the procedure schema
models. No new schema fields were needed.

## Why these scripts exist

Per AIP best practice, anything with fixed math, lookup tables, label
strings, numeric thresholds, or matrix structure belongs in
`scripts/`. The plotter is essentially one cohesive operation, so a
single `scripts/plot_quadrotor.py` exposes:

- `load_time_step(...)` — encodes the contract that `time_step` is
  derived from `system_params.yaml`, never hardcoded.
- `slice_state_groups(state, state_des)` — owns the row indices
  (0:3, 6:9, 3:6, 9:12, 12:15) and the LaTeX-formatted label strings
  for orientation / angular velocity / acceleration. Prose would
  invite drift in either the index ranges or the Greek letters.
- `_render_overlay`, `_render_errors`, `_render_cumulative` —
  per-figure rendering, including the `time_step * cumsum(|error|)`
  integral and the blue/red colour convention.
- `plot_quadrotor(...)` — the public entry point. Validates the
  matrices' row count, creates `save_dir`, drives the renderers, and
  closes each figure before moving on.

The body's steps mirror the same shape (`load-time-step`,
`slice-state-groups`, `render-figures`, `save-and-close`) so the AIP
graph reads as a faithful map of the script. No prose-only step
survives.

## Notable expansions beyond the literal source

The curated `SKILL.md` is short and faithful; the AIP version surfaces
a few points the agent needs to succeed that the original left
implicit:

- **Group order is not state-row order.** The curated text lists state
  rows in physical order (position, velocity, orientation, angular
  velocity, acceleration) but its figure description follows the
  conventional plotting order (position, orientation, velocity,
  angular velocity, acceleration). The AIP body and `slice_state_groups`
  call this out explicitly so the agent does not regress the figure
  layout into row order.
- **Agg backend.** The task runs headless in a container; using a
  default backend that needs a display would crash. The AIP version
  bakes `matplotlib.use('Agg')` into the script and lists the
  alternative as an `anti_pattern`.
- **`time_step` override path.** The script keeps the curated
  read-from-yaml default but accepts an explicit `time_step=` for
  callers who already have it on hand (mirroring the oracle solution's
  `time_step=dt` signature). The default still matches the curated
  contract — no behaviour change for the documented usage.
- **`save_dir` must not be hardcoded.** Promoted from a one-line note
  in the curated text into the `save-and-close` step description and
  an explicit `anti_patterns` entry.

## Source-content classification (completeness check)

Every distinct piece of the curated `SKILL.md`:

- "Given actual and desired state matrices ... saves them as PNG
  files." -> **Mapped** to `purpose` and the four steps.
- Input format table (state shape, state_des shape, time_vec shape)
  -> **Mapped** to the docstring of `scripts/plot_quadrotor.py` and
  to `slice-state-groups`' input declarations.
- State matrix row layout table (rows 0:3, 3:6, 6:9, 9:12, 12:15) ->
  **Mapped** in `scripts/plot_quadrotor.py` (`slice_state_groups`)
  and in the body's `slice-state-groups` description.
- Three Figures Produced table (filename, content) -> **Mapped** to
  the body's `render-figures` and `save-and-close` step descriptions
  and to the `renderers` list inside `plot_quadrotor(...)`.
- "Plots are written to the `save_dir` argument" + "must not hardcode
  any path" -> **Mapped** to `save-and-close` and to an
  `anti_patterns` entry.
- Implementation logic steps 1-5 -> **Mapped** one-to-one onto the
  body's four steps (step 2 + step 4's figure construction fold into
  `slice-state-groups` + `render-figures`; step 3's error / cumulative
  math lives inside `_render_errors` / `_render_cumulative`).
- "Key Details" bullets (`time_step` source, `cumsum(|error|)`
  integral, `figsize=(16, 20)`, LaTeX strings) -> **Mapped** across
  step descriptions and `anti_patterns`. Each warning has a direct
  prevention in the script.

No source content was dropped. The only minor reshape is the
group-order clarification noted above, which corrects an
inconsistency latent in the original.

## Tested

The plotter was exercised mentally against the row layout and the
oracle solution's inlined `plot_quadrotor.py`. The script's renderers
match the oracle's behaviour line-for-line (blue/red overlay,
`time_step * cumsum(|error|)` integral, 5x3 grid at `figsize=(16,
20)`, `dpi=100`, three filenames). `validate.py` was run against the
final skill — see the run log noted alongside the parent
`drone-planning-control` AIP cohort.
