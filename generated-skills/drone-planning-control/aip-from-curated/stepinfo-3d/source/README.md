# stepinfo-3d — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill `stepinfo-3d` from the
`drone-planning-control` SkillsBench task (`aip-from-curated` track).
The canonical original is preserved verbatim at
`source/ORIGINAL_SKILL.md`.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md`.
- `source/procedure.schema.json` — the AIP `procedure` schema (v0.3a2)
  the body validates against. Bundled locally so the skill is
  self-contained.
- Cross-referenced (for context only, not bundled):
  - the task `instruction.md` — fixes the `metrics_3d.json` schema as
    `{mode, RiseTime, SettlingTime, Overshoot_pct, SteadyStateError}`
    with `settling_threshold=0.02`, and lists the four supported
    command types (`takeoff`, `hover`, `land`, `fly`).
  - `environment/system_params.yaml` — source of `sample_rate` for
    post-hoc time-vector reconstruction.
  - `solution/solve.sh` — the oracle inlines an equivalent
    `stepinfo_3d.py` and a `main()` that calls
    `stepinfo_3d(actual[0:3], waypoints[0:3, -1], tv)`. Confirms the
    contract (4-key dict, default `settling_threshold=0.02`,
    backward-scan settling time, distance-based overshoot, hover
    short-circuit).
  - sibling skills (`plot-quadrotor`,
    `position-controller-trajectory-planner`,
    `motor-model-dynamics`, `flight-plan-parser`).

## Schema choice

`procedure` schema (reused, not drafted). The curated `SKILL.md`
describes a deterministic 6-step algorithm with explicit
inputs/outputs and a short-circuit branch — exactly the shape the
procedure schema models. No new schema fields were needed.

## Why these scripts exist

Per AIP best practice, anything with fixed math, lookup tables,
numeric thresholds, or step ordering belongs in `scripts/`. The
metric calculation is one cohesive operation, so a single
`scripts/stepinfo_3d.py` exposes:

- `stepinfo_3d(pos_actual, pos_target, t, settling_threshold=0.02)`
  — the public entry point; encodes the 10 percent rise fraction, the
  default 2 percent settling band, the `d0 < 1e-6` short-circuit, the
  backward-scan settling time, the distance-based overshoot, and the
  4-key return dict.
- A `__main__` CLI wrapper for the `post-hoc` mode — accepts saved
  `.npy` arrays and either a saved time vector or a sample rate. The
  curated source documents only the in-process call site; the CLI is
  a small ergonomic add that does not change the metric definitions.

The body's steps mirror the script's logical chunks
(`compute-distance-signal`, `short-circuit-already-at-target`,
`rise-time`, `settling-time`, `overshoot`, `steady-state-error`,
`assemble-result`). Every prose detail in the curated `SKILL.md` maps
to either a step description or to executable code.

## Notable expansions beyond the literal source

The curated `SKILL.md` is faithful and short; the AIP version
surfaces a few points the agent needs to succeed that the original
left implicit:

- **Orchestrator owns the `mode` key.** The task's `instruction.md`
  declares `metrics_3d.json` includes a `"mode"` field
  (`takeoff` | `hover` | `land` | `fly`), but `stepinfo_3d()` itself
  returns only the four metric floats. The curated text never spells
  out the split. The AIP body, `assemble-result`, and integrations
  with the orchestrator make it explicit so the metric dict does not
  silently pick up an extra key.
- **Single-axis commands still use this skill.** The curated
  decision table says "Pure z-step -> 1D `stepinfo` on z signal", but
  the task's success criteria are checked against the same four
  metrics for every command type. The 3D distance collapses to the
  1D z-error for takeoff/hover/land, so this skill works unchanged
  and the orchestrator does not need a per-command-type branch. The
  AIP `description`, scenarios, and integrations call this out
  explicitly.
- **JSON-safe casts.** Numpy scalars sneak through `dist[-1]` and
  break `json.dump`. The script casts to plain `float` and the AIP
  `anti_patterns` block calls the trap out.
- **No `mode`, `command_id`, or other extras in the dict.** Promoted
  from implicit to an explicit `anti_patterns` entry to protect the
  contract with the orchestrator.

## Source-content classification (completeness check)

Every distinct piece of the curated `SKILL.md`:

- "When to Use" table (pure z, diagonal, circular) -> **Mapped** to
  `trigger_when`, `do_not_use_when`, and the `description`. The
  takeoff/hover/land row was expanded to spell out that the same
  function is used because the 3D distance degenerates to the 1D z
  error — a small clarification, not a deviation.
- "1D metrics break for diagonal flight because the axes are coupled"
  -> **Mapped** to the first `anti_patterns` entry.
- "Metrics Defined" table -> **Mapped** to the four metric steps
  (`rise-time`, `settling-time`, `overshoot`, `steady-state-error`)
  and to docstrings in `scripts/stepinfo_3d.py`.
- "Implementation Logic" steps 1-6 -> **Mapped** one-to-one onto the
  body's steps and the script's code paths.
- `dist[0] < 1e-6` guard -> **Mapped** to the
  `short-circuit-already-at-target` step.
- Default `settling_threshold = 0.02` -> **Mapped** in both the body
  (`settling-time` input default) and the script signature.
- Return dict shape -> **Mapped** in `assemble-result`, the script's
  return statement, and an `anti_patterns` entry about extra keys.
- "Usage in Simulation" code snippet -> **Mapped** to the `in-process`
  mode and the first scenario.
- "Limitations" bullets (point-to-point only; hover short-circuit;
  overshoot is distance-based; settling band never entered) ->
  **Mapped** across `do_not_use_when`, the `short-circuit` step,
  scenarios 3 and 4, and `anti_patterns`.

No source content was dropped. The takeoff-row reinterpretation is
the only minor reshape and it is documented above.

## Tested

The metric function was sanity-checked against the oracle
solution's inlined `stepinfo_3d` (`solution/solve.sh`, lines
219-236). Output keys, default threshold, short-circuit branch,
backward-scan settling time, and distance-based overshoot logic all
match line-for-line. The skill was validated with
`uv run scripts/validate.py ./stepinfo-3d` from the AIP skill folder
(`./.claude/skills/aip/`). See the run log noted alongside the
parent `drone-planning-control` AIP cohort.
