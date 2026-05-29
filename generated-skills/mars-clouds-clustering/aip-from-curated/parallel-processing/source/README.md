# AIP Conversion Notes — parallel-processing

## Source

`vendor/skillsbench/tasks/mars-clouds-clustering/environment/skills/parallel-processing/SKILL.md`

A short reference doc describing how to use `joblib.Parallel` + `delayed` for
CPU-bound batch work, with code blocks covering basic usage, key parameters,
grid search, pre-computing shared data, and performance tips.

## Schema

`procedure.schema.json` — the canonical AIP procedure schema. The skill is a
small workflow (assess → pick params → structure code → run → aggregate),
which is exactly what `procedure` is for. No need for a new schema.

## Script vs Prose

Following AIP guidance ("script the deterministic / mechanical parts; leave
data-dependent judgment in prose"):

- **Scripted** — `scripts/recommend_params.py`. The mapping from task
  properties (CPU- vs I/O-bound, item count, seconds-per-item, progress
  desired) to joblib parameters (`backend`, `n_jobs`, `verbose`) and the
  "is it worth parallelizing?" threshold (0.1s/item from the source) are
  pure lookup-table + numeric rules. Scripting them yields consistent
  parameter choices and surfaces the warnings (memory copy, sub-threshold
  items) without relying on the model to remember.
- **Prose** — defining the per-item worker function, deciding what shared
  data to pre-compute, invoking `Parallel(...)`, and aggregating results.
  These depend on the caller's data shape and what "result" means for the
  task, so they are model-reasoned steps that quote the canonical joblib
  patterns from the source.

## Content Mapping (Source → AIP)

- "Basic Usage" code block → `scenarios[basic-parallel]` + `define-worker` /
  `invoke-parallel` step prose.
- "Key Parameters" (n_jobs, verbose, backend) → encoded in
  `scripts/recommend_params.py` and surfaced in `select-parameters` step.
- "Grid Search Example" → `scenarios[grid-search]` (the Mars task is
  exactly this shape).
- "Pre-computing Shared Data" → `precompute-shared-data` step + scenario.
- "Performance Tips" → encoded in script (0.1s/item threshold, memory
  warning) and `anti_patterns`.

## Deliberate drops

None — every distinct piece of source content maps to a step, scenario,
script behavior, or anti-pattern.
