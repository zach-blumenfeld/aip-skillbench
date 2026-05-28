# Source notes — quadrotor-trajectory-control

This AIP skill was authored from the task instruction at
`vendor/skillsbench/tasks/drone-planning-control/instruction.md` (read
only — no other files in the task were inspected).

## Why this scope
The instruction describes a single coherent unit of work: take a folder
of NL drone commands, plan trajectories that respect per-axis
acceleration limits, simulate a quadrotor with cascade PID, tune the
gains, and emit a fixed `/root/results/<id>/` bundle per command. That
is one skill, not several.

## Mapping from instruction sections to skill content

| Instruction line(s) | Where in skill |
| --- | --- |
| L1–L3 (task summary, four pieces of work) | `purpose` + `steps` |
| L5 (accel limit constraint) | `trajectory_planner.py` + `decisions` first row |
| L7–L37 (output schemas + file list) | `references/output_contract.md` (+ `emit-outputs` step) |
| L19 (`settling_threshold=0.02`) | `metrics.py::compute_metrics` default |
| L40–L44 (success criteria) | `verify-success` step + `tune_gains.py::success` |
| L46–L51 (four command types) | `parse_command.py` regexes + scenarios |

## Schema choice
Reused the canonical `procedure.schema.json` (AIP v0.2). No
schema gap surfaced — every piece of instruction content slotted into
`purpose`, `trigger_when`, `steps`, `decisions`, `scenarios`, or
`anti_patterns`.

## Deliberate drops
None — every line of the instruction is either mapped to a SKILL.md
field, a reference, or a script behavior.
