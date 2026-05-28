# Source materials — geospatial-routing-data (AIP)

## Origin

Compiled from the curated Agent Skill `geospatial-routing-data` shipped with
the `bike-rebalance` SkillsBench task:

    vendor/skillsbench/tasks/bike-rebalance/environment/skills/geospatial-routing-data/SKILL.md

The original is preserved verbatim at `SKILL.original.md` for reference.

## Schema

Uses `procedure.schema.json` (AIP v0.3a2) — bundled in this folder. The skill
is a structured procedure: load → validate → build distances → convert → check.
Every conditional / numerical step is backed by a script.

## Authoring intent

The source skill is mostly Python recipes interleaved with prose rules
("clamp into [-1, 1]", "never assume IDs are 0..n-1", "compare with
tolerance"). All of those are *scriptable logic with fixed thresholds, lookup
tables, or numeric formulas* — exactly what the AIP best-practices guide says
should be pushed into `scripts/` rather than left as prose.

Mapping from source headings to AIP artifacts:

| Source section                        | AIP step                          | Script                                  |
|---------------------------------------|-----------------------------------|-----------------------------------------|
| Parse Data Safely                     | `load-stations-and-depot`         | `scripts/parse_data.py`                 |
| Coordinate Validation                 | (folded into load step)           | `scripts/parse_data.py`                 |
| Great-Circle Distance                 | `compute-distance` (helper)       | `scripts/distance.py`                   |
| Build Routing Nodes                   | `build-arc-distance-matrix`       | `scripts/distance.py`                   |
| Convert Routes Between IDs/Indices    | `convert-routes`                  | `scripts/routes.py`                     |
| Reconstruct Route Distance            | `reconstruct-route-distance`      | `scripts/routes.py`                     |
| Route Data Checks                     | `validate-route-structure`        | `scripts/routes.py`                     |

The "Do not mix" list (Euclidean on degrees, haversine with wrong radius,
mixed units, rounded distances in objective) is encoded as `anti_patterns`.

The Earth-radius default is `3960.0` miles — bike-rebalance declares this
explicitly in `instruction.md`. The distance function accepts `radius` so the
same skill works for any task that declares a different value.

## Deliberate drops

None. Every source rule, code block, and warning lands either in a script,
an `anti_patterns` entry, or a step body. The original 200-line SKILL.md is
fully covered.

## Compatibility

Scripts require Python 3.8+ and only the standard library (`json`, `math`,
`pathlib`). No third-party dependencies.
