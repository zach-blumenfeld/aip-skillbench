# quadrotor-pid-flight — source

Authored from `instruction.md` alone (no inspection of any reference skill or
solution). This README captures the deliberate scope and structure decisions
that don't survive in the compiled `SKILL.md`.

## What the task asks for

Given `system_params.yaml` (mass, inertia, accel limits, ...) and a text command
in one of four templates, produce a `/root/results/<id>/` folder with:

- `metrics_3d.json` (mode + 4 step-response metrics)
- `tuning_results.json` (kp/ki/kd × pos/att, each a length-3 list)
- `planned_trajectory.npy` and `actual_trajectory.npy` (15 × max_iter)
- `plots/` (3 fixed-name PNGs)

Hard constraints:
- Planned trajectory within accel limits at every timestep.
- Per-timestep Euclidean position error < 0.05 m.
- Overshoot < 5%.
- Steady-state error < 0.05 m.

## Skill shape

One procedure-style skill — the task is a single coherent pipeline per
command, not a set of independent capabilities. Schema: `procedure.schema.json`
v0.3a2 (bundled in this folder so the skill travels standalone).

## Step graph (encoded in SKILL.md)

1. `load-system-params` → params dict
2. `parse-command` → {mode, ...}
3. `plan-trajectory` (quintic, accel-clamped) → planned 15×N
4. `tune-pid` (search loop, calls simulate + metrics internally) → gains + actual 15×N
5. `compute-metrics` → mode-aware step-response metrics
6. `generate-plots` → 3 PNGs
7. `write-outputs` → npy + json files with strict schemas
8. `verify-specs` → re-check all four constraints

Every step is script-backed: each contains numeric thresholds, lookup logic,
or fixed-schema output — the kind of work the AIP best-practices explicitly
flag as "must be a script."

## Algorithm choices

- **Trajectory profile.** Quintic minimum-jerk polynomial from rest to rest
  (`s(τ) = 10τ³ − 15τ⁴ + 6τ⁵`). Closed-form peak accel
  `5.7735 · |Δp| / T²` lets the planner check feasibility analytically and
  reject infeasible commands cleanly. No iteration needed.
- **Dynamics.** Standard 6-DOF rigid-body model with ZYX Euler angles +
  first-order motor model. Euler integration at `dt = 0.01 s`.
- **Controller.** Cascaded PID: outer position loop produces a desired
  acceleration vector, which becomes desired thrust magnitude and desired
  roll/pitch (yaw held at 0). Inner attitude loop produces body torques.
- **Tuning.** Defaults are tuned for a ~1 kg quadrotor at near-hover; if specs
  fail, scale-grid search over kp_pos / kd_pos / kp_att-kd_att joint factor
  evaluated against the success rubric.
- **Metrics.** Computed on the dominant-motion axis (z for takeoff/hover/land;
  largest-displacement axis for fly). `settling_threshold=0.02` treated as a
  fraction of step size (industry-standard 2% band).

## Deliberate drops

- **Wind / disturbance modeling.** Not in instruction; sim is deterministic.
- **Quadrotor motor mixing matrix.** Instruction says "drone motor and
  dynamics" but doesn't bound it to four-rotor mixing. The skill keeps the
  motor model at the thrust+torque level (first-order T_actual lag) — generic
  enough to back any rotor count, faithful to the instruction's wording.
- **Yaw control commands.** No yaw appears in any of the four templates;
  yaw is held at 0 throughout.

## Files

- `procedure.schema.json` — bundled schema (procedure v0.3a2).
- `instruction.md` — verbatim copy of the source instruction.
- `README.md` — this file.
