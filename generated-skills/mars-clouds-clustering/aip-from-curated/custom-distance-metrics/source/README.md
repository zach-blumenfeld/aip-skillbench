# Source notes — custom-distance-metrics (AIP)

## Origin

Converted from the curated Agent Skill at:

    vendor/skillsbench/tasks/mars-clouds-clustering/environment/skills/custom-distance-metrics/SKILL.md

The original is bundled here as `SKILL.original.md` for reference.

## Schema choice

Reused `procedure.schema.json` (AIP v0.3a3) rather than drafting a new
schema. The original SKILL.md is a small reference of code patterns for
defining a custom callable metric with sklearn / scipy clustering APIs.
The procedure schema's `purpose` / `trigger_when` / `steps` /
`anti_patterns` shape carries those patterns cleanly: each "section" of
the original becomes a step in the procedure graph that the agent walks
when authoring a custom metric.

## Script vs. prose decisions

Per the AIP best-practices guidance ("script the deterministic/mechanical
parts; leave data-dependent conditional/branching logic as prose"):

- **Prose steps** — all of `identify-metric-need`, `choose-pattern`,
  `wire-into-algorithm`, `tune-performance`. These hinge on agent
  judgement about what the consuming task actually needs (which axes
  matter, whether parameters will be swept, what algorithm consumes the
  metric). Encoding them as scripts would over-restrict.
- **Reference template** — `scripts/weighted_distance_factory.py` is a
  copy-pasteable template that demonstrates the parameterized-factory
  pattern (the most common shape for hyperparameter sweeps). The agent
  reads it as an example to adapt, not as an executable utility — there
  is no domain logic to validate or compute deterministically here.

## Source-content classification

Walking the original `SKILL.md` line-by-line:

| Source content                                | Disposition  | Where in AIP body                                   |
|-----------------------------------------------|--------------|-----------------------------------------------------|
| One-line intro framing                        | Mapped       | `purpose`                                           |
| "Defining Custom Metrics for sklearn" example | Mapped       | `steps.choose-pattern` (callable option) + `wire-into-algorithm` |
| "Parameterized Distance Functions" closure    | Mapped       | `steps.choose-pattern` (factory option) + `scripts/weighted_distance_factory.py` |
| "Example: Manhattan Distance with Parameter"  | Mapped       | `steps.implement-metric` description (referenced as example)   |
| "Using scipy.spatial.distance" cdist/pdist    | Mapped       | `steps.wire-into-algorithm` (scipy branch)          |
| "Performance Considerations" bullets          | Mapped       | `steps.tune-performance` + `anti_patterns`          |
| (none dropped)                                | —            | —                                                   |

## Name preservation

`name: custom-distance-metrics` is preserved verbatim — the task at
`mars-clouds-clustering` mounts skills by directory name, and the
benchmark harness expects this exact slug.
