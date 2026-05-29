# Authoring notes — geospatial-routing-data (AIP conversion)

## Source

Curated Agent Skill at:
`vendor/skillsbench/tasks/bike-rebalance/environment/skills/geospatial-routing-data/SKILL.md`

Bundled here as `source/SKILL.md`.

## Schema choice

`procedure.schema.json` (reused, not drafted). The source is a five-step
execution graph — load + validate the task data, pick the distance metric,
build the distance matrix, convert between IDs and indices, validate the
reported route. The procedure schema's `steps` graph fits this directly,
with optional `inputs` / `outputs` typing the data flowing between steps.

## Script vs prose

This skill is heavily script-dominant. The original `SKILL.md` is a series
of reusable, deterministic Python helpers — coordinate parsing with bounds
checks, ID/index mappings, great-circle distance with a fixed formula and
clamping, arc-set construction over depot_start/stations/depot_end, route
reconstruction in both directions, structural checks, and tolerance compare.
All of these are deterministic with structured inputs — the AIP guidance's
"script the mechanical parts" case.

Everything was consolidated into one importable library plus one CLI:

- `scripts/routing_data.py` — library: `load_routing_data`,
  `great_circle_miles`, `build_node_distances`, `parse_report_route`,
  `route_to_report_ids`, `route_distance_internal`,
  `route_distance_reported_ids`, `check_route_structure`, `assert_close`.
  Also exposes a `validate` CLI subcommand for quick data-file sanity
  checks.
- `scripts/validate_route.py` — CLI: takes `--data` and `--report`,
  recomputes travel distance with the task-supplied Earth radius, runs
  route structural checks per vehicle, optionally compares against an
  expected value with relative + absolute tolerance.

The one deliberate prose-only step is **distance metric choice**. The
agent has to read the task statement and judge which formula, Earth
radius, and unit apply — the AIP guidance treats "conditionals that hinge
on interpreting the input" as exactly the case for a prose step, not a
script. `references/distance-metric-choice.md` documents the judgment.

## Body layout

The body holds the five-node execution graph (with `script:` fields
pointing at the library and the CLI), `anti_patterns` for the gotchas, and
`do_not_use_when` to scope out cases where coordinate handling is
unnecessary (precomputed distance matrix supplied) or where the task uses
a non-great-circle metric.

Detailed integration patterns and the metric-choice judgment guide live in
`references/` so they load on demand:

- `references/distance-metric-choice.md`
- `references/usage-examples.md`

## Source coverage

Every section of the source SKILL.md is mapped:

| Source section                                       | Destination                                                                                            |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Parse Data Safely (`id_to_idx` / `idx_to_id`)        | `routing_data.load_routing_data`                                                                       |
| Coordinate Validation (`parse_location`)             | `routing_data.parse_location` (called inside `load_routing_data`)                                      |
| Great-Circle Distance (radius=3960.0, clamp)         | `routing_data.great_circle_miles` + `references/distance-metric-choice.md`                             |
| Build Routing Nodes (START/END, distances dict)      | `routing_data.build_node_distances`                                                                    |
| Convert Routes Between IDs and Indices               | `routing_data.route_to_report_ids`, `routing_data.parse_report_route`                                  |
| Reconstruct Route Distance + tolerance compare       | `routing_data.route_distance_*`, `routing_data.assert_close`, `scripts/validate_route.py`              |
| Route Data Checks (depot endpoints, IDs, no repeats) | `routing_data.check_route_structure` + `scripts/validate_route.py` per-vehicle pass                    |
| "Do not mix" gotchas                                 | body `anti_patterns`                                                                                   |

No deliberate drops. No schema gaps.

## Name preserved

Per task requirements, the `name:` frontmatter is unchanged:
`geospatial-routing-data`. The destination folder name matches.
