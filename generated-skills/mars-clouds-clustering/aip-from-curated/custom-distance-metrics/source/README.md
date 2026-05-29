# Conversion notes — custom-distance-metrics → AIP

## Source
`SKILL.md.original` is the curated Agent Skill from
`vendor/skillsbench/tasks/mars-clouds-clustering/environment/skills/custom-distance-metrics/SKILL.md`.

## Schema choice
Reused `procedure.schema.json` (the bundled AIP procedure schema). The source
is short and reference-leaning, but the agent's actual job here is procedural:
pick the API surface (sklearn callable vs scipy precomputed matrix), build a
parameterised closure, wire it into the clustering call. That maps cleanly to
the procedure graph (`steps` with `inputs` / `outputs` / `script`). No
purpose-built schema needed.

## Mapping of source content
- "Defining Custom Metrics for sklearn" → step `choose-api-surface` + step
  `wire-metric-into-estimator`.
- "Parameterized Distance Functions" + "Manhattan Distance with Parameter" →
  step `build-parameterised-distance` backed by
  `scripts/build_distance_metric.py`, which carries the closure-factory pattern
  and ready-to-use reference metrics (weighted Euclidean, shape-weighted,
  scaled Manhattan).
- "Using scipy.spatial.distance" → step `precompute-distance-matrix` plus
  `wire-metric-into-estimator` (covers the `metric="precomputed"` path).
- "Performance Considerations" → kept verbatim in the schema under
  `anti_patterns` (the "don't"s) and expanded in `references/performance.md`
  (the "do this instead" detail), referenced from the corresponding step.

## Deliberate drops
None. All five sections of the source SKILL.md are represented in the AIP
body or supporting files.

## Additions beyond the source
- `references/performance.md` adds the coordinate-rescaling equivalence for
  the shape-weighted metric (a `w*x, (2-w)*y` rescale lets `metric="euclidean"`
  reproduce the custom metric at C-path speed). The source SKILL.md hints at
  this under "Performance Considerations" ("consider vectorizing operations")
  without spelling it out; the reference makes it actionable for an agent
  running a large grid search.
- `scripts/build_distance_metric.py` exposes three factory functions so the
  closure pattern is a copy-pasteable import rather than a re-derivation from
  prose.
