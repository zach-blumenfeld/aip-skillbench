# vehicle-dynamics — AIP conversion notes

## Source

`vendor/skillsbench/tasks/adaptive-cruise-control/environment/skills/vehicle-dynamics/SKILL.md`
copied verbatim to `ORIGINAL_SKILL.md` for reference.

## Schema choice

`procedure.schema.json` (bundled here from
`https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json`).

The source skill is a small library of deterministic kinematic primitives an
agent reaches for while building a cruise-control simulation. That's a
graph of script-backed nodes — exactly what `procedure` models. No new
schema was warranted.

## Script vs prose

Every operation in the source is a fixed numeric formula or a closed-form
if/then over numeric inputs:

- speed/position/distance updates — discrete-time arithmetic
- safe-following-distance — `speed * headway + min_distance`
- TTC — division, with a sign guard returning None
- acceleration clamp — `max(min_decel, min(accel, max_accel))`
- mode selection — `cruise`/`follow`/`emergency` from `(lead_present, ttc, threshold)`

All of these are scripted (single file: `scripts/vehicle_dynamics.py`)
per AIP guidance: "Script the deterministic/mechanical parts."
A single file keeps the surface coherent; the functions share no state but
all belong to the same kinematic vocabulary, so splitting would be friction.

## Step graph shape

Steps are independent — no `depends_on` edges. The source skill presents
these as a reference library; an agent calls whichever primitive fits its
current need (e.g., it may compute TTC without updating position first, or
update position in a free-running cruise loop without a lead vehicle). The
procedure schema permits flat lists of script-backed nodes, and that's the
honest shape of the source.

## Content classification (completeness check)

| Source content                                | Disposition                        |
|-----------------------------------------------|------------------------------------|
| Speed update equation                         | Mapped — `update-speed` step       |
| Position update equation                      | Mapped — `update-position` step    |
| Inter-vehicle distance update                 | Mapped — `update-following-distance` step |
| `safe_following_distance` function            | Mapped — `safe-following-distance` step |
| `time_to_collision` function (None on non-approach) | Mapped — `time-to-collision` step |
| `clamp_acceleration` function                 | Mapped — `clamp-acceleration` step |
| `determine_mode` state-machine function       | Mapped — `determine-mode` step     |
| Mode literals `cruise`/`follow`/`emergency`   | Mapped — `mode` output of `determine-mode` |
| Section headings ("Basic Kinematic Model" etc.) | Deliberate drop — organizational only, no information beyond what's in the steps and `purpose`. |

No schema gaps, no body drops.

## Frontmatter

`name: vehicle-dynamics` preserved unchanged — the runtime task mounts the
skill by that exact name.
