# Conversion notes — parallel-processing → AIP

## Source
`SKILL.md.original` is the curated Agent Skill from
`vendor/skillsbench/tasks/mars-clouds-clustering/environment/skills/parallel-processing/SKILL.md`.

## Schema choice
Reused `procedure.schema.json` (the bundled AIP procedure schema). The source
is a short reference, but the agent's task here is procedural: decide whether
parallelisation is worth it, choose a backend, build the worker, dispatch
with `Parallel` + `delayed`, then collect / filter results. That graph maps
cleanly to the procedure schema. No purpose-built schema needed.

## Mapping of source content
- "Basic Usage" → step `dispatch-with-parallel` (the `Parallel(...)(delayed(func)(x) for x in items)` shape).
- "Key Parameters" (`n_jobs`, `verbose`, `backend`) → step `choose-backend` plus the `n-jobs` input on `dispatch-with-parallel`; rationale lives in `references/performance.md`.
- "Grid Search Example" → step `dispatch-with-parallel` (via the `parallel_grid_search` factory in `scripts/parallel_grid_search.py`) plus `collect-and-pick-best` for the filter + `max(..., key=...)` tail.
- "Pre-computing Shared Data" → step `pre-compute-shared-data` backed by `scripts/parallel_grid_search.py::parallel_with_shared`.
- "Performance Tips" — the > 0.1 s / overhead point becomes `decide-parallel-worthwhile` backed by `_should_parallelise`; memory caveats and `verbose` guidance are kept in `references/performance.md`; the "watch memory" warning shows up in `anti_patterns`.

## Deliberate drops
None. Every section of the source SKILL.md is represented in the AIP body or
the supporting `scripts/` / `references/` files.

## Additions beyond the source
- `scripts/parallel_grid_search.py` exposes three factory functions
  (`parallel_map`, `parallel_grid_search`, `parallel_with_shared`) plus
  `pick_best`. Each wrapper folds in the "is it worth parallelising?" guard
  rail so the call site does not need to branch — the source describes the
  decision as a tip, the script encodes it.
- `references/performance.md` expands the one-line "performance tips" section
  into actionable guidance on backend choice, memory pitfalls, nested
  parallelism, and when *not* to use joblib (BLAS-saturated workloads).
