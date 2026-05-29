# vehicle-dynamics — AIP conversion notes

## Source

Translated from the curated Agent Skill at
`vendor/skillsbench/tasks/adaptive-cruise-control/environment/skills/vehicle-dynamics/SKILL.md`
(preserved verbatim here as `SKILL_original.md`).

## Schema choice

`procedure.schema.json` (canonical AIP procedure schema, v0.3a2).

The source is presented as a small library of primitives — kinematic updates,
safe-distance formula, TTC, acceleration clamp, mode state machine — that the
agent composes inside its own simulation loop. AIP procedure with one
script-backed step per primitive fits naturally: each primitive is a node in
the agent's execution graph; the agent chooses which to call per timestep.
No new schema needed.

## Why scripts

Every primitive in the source is a numeric calculation, threshold, or clamp.
Per AIP best practices, scriptable logic must live in `scripts/`, not prose.
All five primitives are co-located in a single `scripts/vehicle_dynamics.py`
module — they form a coherent library and the AIP guidance prefers fewer
script files when the logic belongs together.

## Completeness mapping (source → AIP body)

| Source section                | Where it lives in the AIP skill                                         |
|-------------------------------|-------------------------------------------------------------------------|
| Speed Update                  | `update_speed` in `scripts/vehicle_dynamics.py` (step `update-kinematics`) |
| Position Update               | `update_position` in `scripts/vehicle_dynamics.py` (step `update-kinematics`) |
| Distance Between Vehicles     | `update_distance` in `scripts/vehicle_dynamics.py` (step `update-kinematics`) |
| Safe Following Distance       | `safe_following_distance` (step `compute-safe-distance`)                |
| Time-to-Collision (TTC)       | `time_to_collision` with the None-when-receding edge case (step `compute-ttc`) |
| Acceleration Limits           | `clamp_acceleration` (step `clamp-acceleration`)                        |
| State Machine Pattern         | `determine_mode` (step `select-mode`)                                   |
| `max(0, new_speed)` guard     | Preserved inside `update_speed`; surfaced as anti-pattern               |
| `relative_speed <= 0 -> None` | Preserved inside `time_to_collision`; surfaced as anti-pattern          |
| Mode precedence order         | Preserved inside `determine_mode`; surfaced as anti-pattern             |

No source content was dropped.
