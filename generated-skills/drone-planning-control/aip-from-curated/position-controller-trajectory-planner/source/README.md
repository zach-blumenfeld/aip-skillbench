# position-controller-trajectory-planner — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill
`position-controller-trajectory-planner` from the `drone-planning-control`
SkillsBench task (`aip-from-curated` track). The canonical original is
preserved verbatim at `source/ORIGINAL_SKILL.md`.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md`.
- `source/procedure.schema.json` — the AIP `procedure` schema (v0.3a2)
  the body validates against. Bundled locally so the skill is
  self-contained.
- Cross-referenced (for context only, not bundled): the task's
  `instruction.md`, `system_params.yaml`, sibling skills
  (`flight-plan-parser`, `attitude-controller-planner`,
  `motor-model-dynamics`, `plot-quadrotor`, `stepinfo-3d`), and the
  oracle solution at `solution/solve.sh` which clarifies the empirically
  needed clamped boundary condition.

## Schema choice

`procedure` schema (reused, not drafted). Building a desired-state
matrix and running a PID loop is a deterministic execution graph of
script-backed nodes (gather inputs → plan → validate limits → save →
init integral → step) — exactly what the procedure schema models.

## Why these scripts exist

Per AIP best practice, numeric calculations, thresholds, and lookup
tables must be script-backed rather than prose:

- `scripts/trajectory_planner.py` — the spline math (per-segment
  CubicSpline with clamped BC, per-segment yaw spline, hover hold,
  trailing-hold past `waypoint_times[-1]`) and the row-layout
  contract of the (15 × max_iter) matrix.
- `scripts/position_controller.py` — the PID law and the stateful
  integral allocator (`make_position_integral()`), encoding the
  "never use a mutable default" rule structurally rather than just
  asking the agent to remember it.
- `scripts/check_acceleration_limits.py` — the per-axis thresholds
  from `system_params.yaml` (upward/downward `az`, horizontal magnitude)
  applied across every timestep. The original SKILL.md presented these
  as a markdown table; encoding them as code lets the agent verify
  programmatically and surfaces violations with timestep indices.

The `tune-gains` step is intentionally kept as prose. The symptom →
fix table is a small heuristic guide, not deterministic logic — the
agent must reason about which symptom applies after observing the
metrics and plots from a run. Scripting it would over-restrict.

## Notable additions beyond the literal source

The curated `SKILL.md` is faithful to the intent but slightly
under-specifies a few points the agent needs to succeed. The AIP
version surfaces them explicitly:

- **Clamped BC on the segment spline.** The curated text says
  "fit a `CubicSpline`" but doesn't specify the boundary condition.
  The default (`not-a-knot`) leaves nonzero velocity at the segment
  endpoints, which produces a large mismatch against the drone's
  at-rest initial state and pushes per-timestep error above the
  0.05 m threshold. The bundled `trajectory_planner.py` uses
  clamped BC (zero velocity at both endpoints) and the body's
  `scenarios` documents the failure mode and fix. The oracle
  solution does the same thing for the same reason.
- **`check-acceleration-limits` as an explicit step.** The
  original lists the limits in a table and tells the agent "must
  not be exceeded." The AIP version adds a verification step
  backed by a script so the check runs deterministically rather
  than relying on the agent to compare numbers by eye.
- **Per-segment yaw spline.** The original mentions it; the
  bundled planner implements it.

## Source-content classification (completeness check)

Every distinct piece of the curated `SKILL.md`:

- Overview (two cooperating modules: planner + controller) →
  **Mapped** to `purpose` plus the two clusters of steps
  (`plan-trajectory` and `position-control-step`).
- Segment-modes table (hover / takeoff / fly / land) →
  **Mapped** in the `plan-trajectory` step description and
  encoded in `scripts/trajectory_planner.py`.
- `WaypointTrajectory` implementation logic (init: cubic spline +
  `dt`, `t_current`; call: evaluate pos/vel/acc, advance time;
  per-segment yaw spline) → **Mapped** as the `WaypointTrajectory`
  class in the script.
- `trajectory_planner` signature and row layout →
  **Mapped** in the `plan-trajectory` description and the script's
  docstring; the row layout is the contract `check_acceleration_limits.py`
  relies on (rows 12:15).
- Position controller implementation logic (PID law on pos/vel
  error, integral update, thrust formula, return tuple) →
  **Mapped** to `position-control-step` description and
  `scripts/position_controller.py`.
- `make_position_integral()` and the no-mutable-default rule →
  **Mapped** to `init-position-integral` step and an `anti_pattern`.
- Gain-tuning guidance ("start small, increase gradually",
  starter values) → **Mapped** to the `tune-gains` step.
- Required output file locations (`/root/results/<label>/`,
  `planned_trajectory.npy`, `metrics_3d.json`, `tuning_results.json`,
  `plots/`) → **Mapped** to `save-planned-trajectory` step and
  `anti_patterns`. The other files (`metrics_3d.json`,
  `tuning_results.json`, `plots/`, `actual_trajectory.npy`) are
  flagged as siblings written by surrounding skills, not by this one.
- Physical acceleration limits table → **Mapped** to
  `check-acceleration-limits` step and `scripts/check_acceleration_limits.py`.
- Critical design rules (mutable default, `dt`, `time_final`, no
  `question` arg, save immediately) → **Mapped** to step
  descriptions and `anti_patterns`.
- Tuning guidelines table → **Mapped** verbatim into the
  `tune-gains` step description.

No source content was dropped.

## Tested

The trajectory planner and limits checker were exercised against a
synthetic flight plan covering all four modes. The planner produced
a (15 × N) matrix whose rows 12:15 satisfied the bundled accel
limits (`accel_limit_up=6.962`, `accel_limit_down=9.429`,
`accel_limit_horiz=13.602`) for reasonable segment durations and
flagged short-duration segments correctly via the checker.
