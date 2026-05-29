---
name: parallel-processing
description: Parallel processing with joblib for grid search and batch computations. Use when speeding up computationally intensive tasks across multiple CPU cores.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Speed up batch and grid-search style Python work by fanning it out across
  CPU cores with joblib's `Parallel` + `delayed`. Covers the four decisions
  that decide whether parallelisation actually helps: is per-item cost high
  enough to overcome dispatch overhead, what backend (loky vs threading)
  fits the workload, how to share large read-only data without paying the
  pickling cost per call, and how to collect / filter results.

trigger_when:
  - Running the same Python function over many inputs (grid search,
    hyperparameter sweep, per-image processing, per-row scoring).
  - A loop or comprehension is the bottleneck and per-iteration cost is
    non-trivial (> ~0.1 s).
  - Fitting / scoring an sklearn estimator across a parameter grid that has
    no built-in parallel runner.
  - User asks to "parallelise", "speed up", "use all cores", or mentions
    joblib, Parallel, delayed, or n_jobs.

do_not_use_when:
  - The hot loop is already vectorised through numpy / scipy / sklearn and
    BLAS-level threading is saturating cores — adding joblib on top
    oversubscribes and slows things down.
  - Per-item cost is sub-millisecond — dispatch overhead dominates; just
    run sequentially.
  - The library you are calling already exposes its own parallelism
    (sklearn's `n_jobs=`, xgboost `nthread=`, etc.). Use that instead of
    wrapping it.
  - The task is I/O-bound against an external service with strict rate
    limits — parallelism trips the rate limiter before it helps.

steps:
  - name: decide-parallel-worthwhile
    description: >
      Estimate per-item cost and item count. If per-item cost < 0.1 s OR
      item count < 8, return `sequential` and skip the rest. Otherwise
      return `parallel` and continue. Heuristics live in
      `scripts/parallel_grid_search.py` (`_should_parallelise`,
      `MIN_ITEMS_FOR_PARALLEL`, `MIN_PER_ITEM_SECONDS`); see
      `references/performance.md` for the rationale.
    script: scripts/parallel_grid_search.py
    inputs:
      - name: item-count
        type: integer
      - name: per-item-seconds
        type: float
        nullable: true
        description: Rough estimate of one worker's runtime. Pass `null` when unknown; the heuristic then falls back to the item-count check only.
    outputs:
      - name: decision
        type: string
        description: One of `parallel`, `sequential`.
    one_of:
      - parallel
      - sequential

  - name: choose-backend
    description: >
      Pick `loky` for CPU-bound work (default — separate processes, sidesteps
      the GIL) or `threading` for I/O-bound work (HTTP, disk, GPU calls).
      When unsure, start with `loky`. See `references/performance.md`
      § Backend choice.
    depends_on:
      - decide-parallel-worthwhile
    inputs:
      - name: workload-shape
        type: string
        description: "`cpu-bound` or `io-bound`."
    outputs:
      - name: backend
        type: string
    one_of:
      - loky
      - threading

  - name: pre-compute-shared-data
    description: >
      If every task needs the same large read-only object (dataset, fitted
      estimator, lookup table), build it once outside the worker and pass
      it positionally via `delayed(func)(item, shared)`. With `loky` each
      worker still receives a pickled copy — watch RAM. For very large
      objects pass a handle (filename, dataset id) and let the worker load
      it. Use `scripts/parallel_grid_search.py::parallel_with_shared` as
      the template.
    script: scripts/parallel_grid_search.py
    inputs:
      - name: shared-needed
        type: boolean
    outputs:
      - name: shared
        type: object
        nullable: true
        description: The pre-built shared object, or `null` when the task takes only its own item.

  - name: dispatch-with-parallel
    description: >
      Call `Parallel(n_jobs=-1, verbose=10, backend=backend)(delayed(func)(x) for x in items)`.
      Use `n_jobs=-1` for all cores, `n_jobs=1` for sequential debugging,
      or a specific cap when sharing the machine or workers are memory-heavy.
      `scripts/parallel_grid_search.py` exposes three ready-to-import
      wrappers: `parallel_map`, `parallel_grid_search` (cartesian product
      over a `dict` of param lists), and `parallel_with_shared`. Each
      wrapper falls back to sequential when `decide-parallel-worthwhile`
      would have said so, so callers do not need to branch.
    script: scripts/parallel_grid_search.py
    depends_on:
      - decide-parallel-worthwhile
      - choose-backend
    inputs:
      - name: func
        type: object
        description: The worker callable. Must be picklable when `backend` is `loky`.
      - name: items
        type: list[object]
        description: Iterable of inputs (for `parallel_map`) or precomputed parameter combinations.
      - name: grid
        type: object
        nullable: true
        description: Dict of parameter name to list of values, when running a grid search.
      - name: shared
        type: object
        nullable: true
      - name: backend
        type: string
      - name: n-jobs
        type: integer
    outputs:
      - name: raw-results
        type: list[object]
        description: One entry per dispatched call. May include `None` for tasks the worker chose to skip.

  - name: collect-and-pick-best
    description: >
      Filter `None` results (the idiomatic "drop this combination" return
      value) and, for grid searches, pick the best by score. Use
      `scripts/parallel_grid_search.py::pick_best` for the max-by-score
      pattern.
    script: scripts/parallel_grid_search.py
    depends_on:
      - dispatch-with-parallel
    inputs:
      - name: raw-results
        type: list[object]
      - name: score-key
        type: string
        nullable: true
        description: Key to maximise across results (e.g. `score`, `silhouette`). Omit when the caller only needs the filtered list.
    outputs:
      - name: results
        type: list[object]
        description: "`raw-results` with `None`s dropped."
      - name: best
        type: object
        nullable: true
        description: Single best row when `score-key` is provided.

scenarios:
  - need: Grid search over `(eps, min_samples)` for DBSCAN on a fixed point cloud.
    context: >
      The point cloud is the same for every cell, so it qualifies as shared
      data. ~120 cells, each fit takes ~0.3 s, so the parallel guard rails
      fire `parallel`.
    action: >
      `pre-compute-shared-data` loads the points once.
      `dispatch-with-parallel` calls
      `parallel_grid_search(evaluate, grid={"eps": [...], "min_samples": [...]})`
      with the points captured by closure or passed via
      `parallel_with_shared`. `collect-and-pick-best` filters `None`s
      (cells that produced 0 clusters) and picks the highest silhouette.
    outcome: >
      All 120 fits complete in roughly `120 * 0.3 / n_cores` seconds plus
      worker startup, returning the best `(eps, min_samples)`.

  - need: Apply the same heavy per-image transform to 4000 images.
    context: >
      Per-image cost is ~1.5 s and items are independent. Each worker
      already loads its own image, no shared object needed.
    action: >
      `decide-parallel-worthwhile` -> `parallel`. `choose-backend` ->
      `loky`. `dispatch-with-parallel` uses `parallel_map(transform,
      image_paths)`. `collect-and-pick-best` returns the list (no score key).
    outcome: 4000 images processed across all cores; results returned in input order.

  - need: Query a slow REST endpoint for 200 ids.
    context: >
      Workload is I/O-bound, not CPU-bound. The endpoint's rate limit is
      well above the planned concurrency.
    action: >
      `choose-backend` -> `threading` (no process fork / pickling cost,
      threads share the request session). `dispatch-with-parallel`
      calls `parallel_map(fetch, ids, backend="threading")`.
    outcome: All 200 fetches complete while respecting the rate limit.

anti_patterns:
  - Parallelising a tight per-item loop where each call is < 1 ms — joblib
    overhead dwarfs the work.
  - Stacking joblib on top of code that is already saturating BLAS threads
    (numpy / scipy / sklearn). The cores end up oversubscribed and the
    wall-clock gets worse.
  - Passing a large array to `delayed(...)(big_array, ...)` for every call
    when the array is the same. Each loky worker pickles its own copy;
    bind it once at module / closure scope instead.
  - Using `backend="threading"` for CPU-bound numpy crunching — the GIL
    eats the win.
  - Wrapping an sklearn estimator that already exposes `n_jobs=` in a
    joblib `Parallel` block. Use the built-in instead.
  - Forgetting to filter `None` results before computing `max(...)` —
    yields a `TypeError` deep in the call.
  - Nested parallelism — a `Parallel(...)` block whose worker itself calls
    another `Parallel(...)`. Either oversubscribes the CPU or fights the
    GIL. Parallelise only the outer loop.
```
