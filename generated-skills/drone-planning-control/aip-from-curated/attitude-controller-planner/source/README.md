# attitude-controller-planner — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill
`attitude-controller-planner` from the `drone-planning-control`
SkillsBench task (`aip-from-curated` track). The canonical original
is preserved verbatim at `source/ORIGINAL_SKILL.md`.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md`.
- `source/procedure.schema.json` — the AIP `procedure` schema
  (v0.3a2) the body validates against. Bundled locally so the skill
  is self-contained.
- Cross-referenced (for context only, not bundled): the task's
  `instruction.md`, `system_params.yaml`, the oracle at
  `solution/solve.sh`, and the sibling skills
  (`position-controller-trajectory-planner`, `motor-model-dynamics`,
  `flight-plan-parser`, `plot-quadrotor`, `stepinfo-3d`).

## Schema choice

`procedure` schema (reused, not drafted). The inner loop is a
deterministic execution graph of script-backed nodes (gather inputs
-> attitude planner step -> init integral -> attitude controller
step) with one prose-style tuning node — exactly what the procedure
schema models. The sibling skills in this task already validate
against the same schema, which keeps the corpus consistent.

## Why these scripts exist

Per AIP best practice, numeric calculations, lookup tables, and
mutable-state allocators must be script-backed rather than prose:

- `scripts/attitude_planner.py` — the inverse-kinematics expression
  `(phi_des, theta_des) = f(ax, ay, psi, g)` and the yaw / yaw-rate
  passthrough. Encoding the trig as code keeps the sign convention
  fixed (`phi_des = (1/g)(ax sin psi - ay cos psi)`) so the agent
  cannot silently flip a sign during a rewrite.
- `scripts/attitude_controller.py` — the PID law, the element-wise
  gain multiply before the inertia `@`, and the
  `make_attitude_integral()` allocator. Encoding
  `make_attitude_integral()` as a function rather than a prose rule
  ("never use a mutable default") makes the correct pattern the
  default — the agent calls the constructor, gets a fresh dict, and
  passes it in explicitly.

The `tune-gains` step is intentionally kept as prose. The
symptom -> fix table is a heuristic guide, not deterministic logic —
the agent must observe metrics and plots from a run and reason
about which symptom applies. Scripting it would over-restrict.

## Notable additions beyond the literal source

The curated `SKILL.md` is faithful to the intent but slightly
under-specifies a few points the agent needs to succeed against the
full task. The AIP version surfaces them explicitly:

- **Bundled-default gains as a landing point.** The curated text
  opens with a deliberately gentle starter
  (`kp_att = [100, 100, 50]`, ki/kd all zero) and instructs the
  agent to raise gradually, but does not state a known-good
  endpoint. The oracle's
  `kp_att = [400, 400, 200]`, `ki_att = [0.5, 0.5, 0.5]`,
  `kd_att = [40, 40, 28]` is recorded in `scripts/attitude_controller.py`
  and called out in the `tune-gains` step so the agent has a
  defensible target rather than a blind walk.
- **Explicit assignment back onto `desired_state.rot` /
  `desired_state.omega`.** The curated text describes the planner
  returns `rot` and `omega` but does not name the assignment back
  onto the desired state struct that the controller will read.
  The `attitude-planner-step` step and `integrations` block make
  this composition explicit (`ds.rot, ds.omega = attitude_planner(ds,
  params)`).
- **Explicit per-axis gain ordering and element-wise rule.** The
  original mentions "gains are arrays [phi, theta, psi]; multiply
  element-wise"; the AIP version turns this into an `anti_pattern`
  and ties it to the script docstring.

## Source-content classification (completeness check)

Every distinct piece of the curated `SKILL.md`:

- "Overview" (two cooperating modules: planner + controller) ->
  **Mapped** to `purpose` plus the two clusters of steps
  (`attitude-planner-step`, `attitude-control-step`).
- "Attitude Planner -> Implementation Logic"
  (`phi_des = (1/g)(ax sin psi - ay cos psi)`,
  `theta_des = (1/g)(ax cos psi + ay sin psi)`,
  return `rot` and `omega`) ->
  **Mapped** in the `attitude-planner-step` description and
  encoded literally in `scripts/attitude_planner.py`.
- "Attitude Controller -> Implementation Logic"
  (error -> integral accumulate -> moment computation with inertia
  multiply) -> **Mapped** to `attitude-control-step` and encoded in
  `scripts/attitude_controller.py`.
- `make_attitude_integral()` and the "never use a mutable default"
  rule -> **Mapped** to `init-attitude-integral` step and an
  `anti_pattern`. The allocator function is the structural
  encoding.
- "Gain Tuning" (no fixed range; start small; example starter
  values `kp_att = [100, 100, 50]`, zeros for ki/kd) -> **Mapped**
  to the `tune-gains` step.
- "Critical Design Rules" — mutable-default ban, `ki_att <= 0.5`,
  `dt = 1.0 / params['sample_rate']`, element-wise gain rule ->
  **Mapped** across step descriptions and four corresponding
  `anti_patterns`.
- "Tuning Guidelines" symptom -> fix table -> **Mapped** verbatim
  into the `tune-gains` step description.
- "Integration in Main Loop" code snippet ->
  **Mapped** to the `position-controller-trajectory-planner` and
  `motor-model-dynamics` entries in `integrations` and reinforced
  in the `attitude-planner-step` / `attitude-control-step`
  descriptions.

No source content was dropped.

## Tested

The bundled `scripts/attitude_planner.py` and
`scripts/attitude_controller.py` are identical in math and
signatures to the oracle's `attitude_planner.py` and
`attitude_controller.py` (oracle is the canonical reference for
this task and is known to satisfy the success criteria across the
provided commands). Sanity-checked locally that
`make_attitude_integral()` returns a fresh `{"e": zeros(3)}`
mapping, and that `attitude_planner` returns the expected zero
roll/pitch when `ax = ay = 0`.
