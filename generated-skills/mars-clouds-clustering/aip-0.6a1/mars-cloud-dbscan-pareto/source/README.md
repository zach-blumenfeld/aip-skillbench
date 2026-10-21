# Source and provenance: mars-cloud-dbscan-pareto

## Provenance
Compiled on 2026-10-20 from three curated Agent Skills, copied here verbatim:

| Source | Path |
|---|---|
| custom-distance-metrics | `source/custom-distance-metrics/SKILL.md` |
| parallel-processing | `source/parallel-processing/SKILL.md` |
| pareto-optimization | `source/pareto-optimization/SKILL.md` |

The three source skills are generic. The task-specific contract comes from the task
statement the downstream agent receives ("Mars Cloud Clustering Optimization"): the data
layout, the grid, the metric, matching, averaging, the filter, and the output format. That
contract is in `scripts/`, `assets/config.json`, `references/method.md`, and the SKILL.md
anti-patterns. The data facts were checked against the real task files: 25,856 citizen-science
rows and 1,940 expert rows, 369 images in each file, the `file_rad` key formatted like
`080109120000/080110120000_A3.png`, and no missing x/y.

## Intent
Given the two annotation CSVs, compute the full grid search and write the Pareto frontier
CSV, recomputed from whatever files are given. Nothing is hardcoded from a previous run.

## Component-kind choices
| Step | Kind | Why |
|---|---|---|
| inspect-data | execution | Loading, type coercion, key matching, and anomaly counts are deterministic. Hard failures exit non-zero so the run stops early. |
| data-gate | router | Branches on the script's `data_status` (clean or warnings). |
| review-warnings | client_task | Whether an anomaly is benign or means the wrong inputs takes judgment over the report. The template carries how each rule treats each warning type. Its written verdict is the output; a blocking verdict stops the run. |
| grid-search | execution | DBSCAN, the custom metric, centroids, greedy matching, F1/delta, and averaging are all numeric rules. Parallelized with joblib per the parallel-processing source. |
| pareto-frontier | execution | The filter, the dominance test, rounding, and the CSV format are deterministic. paretoset (pareto-optimization source) is cross-checked against the source's manual dominance definition. |
| frontier-gate | router | Branches on `frontier_status` (found or empty). |
| diagnose-empty | client_task | Explaining an empty frontier (hard data or a key/scale bug) is synthesis over the summaries. The header-only CSV stays as the spec-correct output. |

Design notes:
- The custom metric is applied as a precomputed distance matrix built with the exact
  formula `sqrt((w*dx)^2 + ((2-w)*dy)^2)`. Labels come from sklearn's DBSCAN core loop
  (`_dbscan_inner`), run once per distinct core set, with a connected-components fallback
  that gives identical labels. In testing this gave the same averaged F1 and delta as
  sklearn with a Python callable metric (custom-distance-metrics pattern), and the same
  results for all 847 combinations as per-combination `DBSCAN(metric="precomputed")`
  calls. It follows that source's own advice: "Pre-compute distance matrices when doing
  multiple lookups", "consider vectorizing".
- Why so much optimization: the `aip run` client kills a script after 60 s. A
  per-combination `DBSCAN()` grid took 32 s or more locally and timed out under load. The
  grid step also checkpoints image chunks under `work_dir`, so a resume after a timeout
  finishes the job.
- joblib uses `backend="multiprocessing"` rather than the source's default loky backend.
  With the container's joblib 1.3.2 on Python 3.12, loky workers print ResourceTracker
  tracebacks on stderr at exit. Results are identical.
- Exact ties on (F1, delta) are kept (`distinct=False`). The pareto-optimization source
  defines dominance as "at least as good in all, strictly better in at least one", and its
  manual implementation keeps ties. paretoset's default `distinct=True` would drop them.
- The grid defaults to the task's standard grid (`assets/config.json`). A `search_space`
  start input can override it when an instance states a different grid.

## Completeness check: where each source item lives
custom-distance-metrics
- sklearn DBSCAN accepts a callable metric: `references/method.md` step 2, the anti-pattern
  on callables, and the precomputed equivalent in `scripts/grid_search.py`
  (`shape_distance_matrix`).
- Parameterized distance via closure/factory (weight_x, weight_y): the shape-weighted metric
  with weights w and 2-w (`grid_search.py`, `method.md`).
- scipy `cdist` for distance matrices: `grid_search.greedy_match` uses `cdist` for the
  Euclidean centroid-to-expert matrix.
- Performance (custom Python functions are slow; vectorize; precompute matrices): the
  precomputed matrix, built once per (image, w), plus the anti-pattern.

parallel-processing
- joblib `Parallel(n_jobs)(delayed(f)(...))` and grid search over `itertools.product`:
  `grid_search.main` runs work-balanced image chunks in parallel, each looping over the
  full (min_samples, epsilon, shape_weight) grid.
- n_jobs semantics: `n_jobs = cpu_count` (`grid_search.py`, `method.md` Performance).
- backend (loky for CPU-bound work): replaced by `multiprocessing` for the reason in the
  design notes (`method.md` Performance).
- Pre-compute shared data once and pass it to tasks: the per-image arrays are built once
  and passed to each task.
- Filter None results and pick the best: `grid_summary.best_f1` and its parameters; the
  F1 > 0.5 filter is in `pareto_frontier.py`.
- Tips (only worth it for tasks over 0.1 s; memory copies per worker; verbose): tasks are
  coarse image chunks, and only each chunk's small point arrays are copied (`method.md`).

pareto-optimization
- Dominance definition and the frontier as the non-dominated set: `pareto_frontier.non_dominated`
  and `method.md` Selection.
- paretoset with sense max/min: `pareto_frontier.py` (F1 max, delta min).
- Manual implementation: vectorized as `non_dominated` and used as a cross-check (the step
  fails if the two disagree).
- Model-selection example (filter by threshold, then mask, sort, and save to CSV): F1 > 0.5
  filter, sort by F1 descending, `to_csv(index=False)` with the task's column order.
- Properties (trade-off curve, no single best): implied by keeping the whole frontier.

## Deliberate drops
- custom-distance-metrics "Example: Manhattan Distance with Parameter": an illustrative
  alternative metric. The task fixes the metric, so it is not actionable here.
- custom-distance-metrics `pdist`/`squareform` snippet: redundant with the precomputed
  matrix built by numpy broadcasting (same result, no Python callback).
- parallel-processing "Sequential vs parallel" basic `x ** 2` example and the
  `backend='threading'` option for I/O-bound work: background; the work here is CPU-bound.
- parallel-processing `verbose=10` progress output: dropped because script stdout must be
  exactly one JSON object (joblib's verbose output goes to stderr, but it adds noise and no
  information). Elapsed time is reported in `grid_summary` instead.
- pareto-optimization "Visualization" (matplotlib): the task wants only a CSV, and
  matplotlib is not in the container.
- pareto-optimization example data (accuracy/latency, batch_size/hidden_units): illustrative
  data only. The pattern it shows is kept.

## Functional test log (2026-10-20, `aip run` / `aip resume`)
| Input | Path through the graph | Result |
|---|---|---|
| Real task files (369 images) | inspect-data → clean → grid-search → pareto-frontier → found → end | 20-row frontier. Matches per-combination sklearn `DBSCAN` and a naive callable-metric implementation. All 847 rows are bit-identical under Python 3.12 / sklearn 1.3.2 / numpy 1.26.4 (the container's versions). |
| Variant A: 150 images, 12 with no citizen-science points, 5 blank-x rows, 1 citizen-science-only image | inspect-data → warnings → review-warnings (answered "proceed") → grid → found → end | 15-row frontier. The top rows match the naive implementation, with F1 zeros averaged in. |
| Variant B: expert points shifted by (+400, −300) px | clean → grid → empty → diagnose-empty (answered) → end | Header-only CSV, best F1 0.0119. This run surfaced a gap: the report lacked the expert coordinate ranges the diagnosis needs, so they were added. |
| Missing file or a shape_weight outside (0, 2) | inspect-data exits 1 with a named error | Fails early, as designed. |
| First `aip run` with per-combination `DBSCAN()` calls | grid-search timed out at the client's 60 s limit | Led to the dbscan_inner, caching, and checkpoint redesign. Resume reuses finished chunks (verified: 72 of 72 reused). |
