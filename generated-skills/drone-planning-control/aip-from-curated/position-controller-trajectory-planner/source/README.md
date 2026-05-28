# Conversion notes

Source skill:
`vendor/skillsbench/tasks/drone-planning-control/environment/skills/position-controller-trajectory-planner/SKILL.md`

The original is a freeform-markdown Agent Skill describing two cooperating
modules — a cubic-spline trajectory planner and a position PID controller —
that together form the outer control loop for a quadrotor.

The schema chosen is `procedure.schema.json` (bundled here) because the
content is a structured implementation procedure: ordered steps to build
each module, signal-to-action tuning decisions, and an anti-pattern list
of critical design rules. The `name` field is preserved verbatim so the
benchmark harness mounts the skill at the same path.

Mapping of source sections to AIP body fields:

- Overview, Trajectory Planner segment modes / signature, Position Controller
  logic, Saving the Planned Trajectory, Required Output File Locations,
  Physical Acceleration Limits → `steps` (one per implementation phase).
- Tuning Guidelines table → `decisions` (signal → action).
- Critical Design Rules → `anti_patterns`.
- Gain Tuning starter values → folded into the `tune-gains` step.

Nothing from the source is deliberately dropped.
