---
name: parallel-processing
description: Parallel processing with joblib for grid search and batch computations. Use when speeding up computationally intensive tasks across multiple CPU cores.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Distribute computationally intensive batch work across CPU cores using
  joblib's Parallel + delayed primitives. Covers parameter selection
  (n_jobs, backend, verbose), pre-computing shared data so workers don't
  redo it, the grid-search shape, and the overhead threshold below which
  parallelization is not worth it.

trigger_when:
  - Running a grid search or sweep over hyperparameters where each
    combination is independently evaluable.
  - Looping over many items (images, files, rows) where the per-item work
    takes a non-trivial amount of time and items don't depend on each
    other.
  - A sequential loop is taking too long and the per-iteration work is
    CPU-bound rather than waiting on I/O.

do_not_use_when:
  - Per-item work takes well under 0.1s — joblib's process-startup and
    serialization overhead will exceed the savings.
  - Workers need to share mutable state (use a different concurrency
    model — multiprocessing.Manager, a queue, etc.).
  - The loop is already vectorized with NumPy / pandas; vectorization
    usually wins over Parallel-over-delayed.

steps:
  - name: assess-task-shape
    description: >
      Identify the unit of work. Estimate (or measure with one item) the
      seconds-per-item. Classify as CPU-bound (numeric computation,
      clustering, model fitting) or I/O-bound (HTTP, disk reads). Count
      the items.
    outputs:
      - name: task-type
        type: string
        description: "'cpu_bound' or 'io_bound'."
      - name: n-items
        type: integer
      - name: seconds-per-item
        type: float
        description: Estimated wall-clock seconds for one item, sequentially.
      - name: progress-wanted
        type: boolean
        description: Whether to emit joblib progress output.

  - name: select-parameters
    description: >
      Recommend Parallel() parameters (n_jobs, backend, verbose) from the
      assessed task properties. Returns the call snippet and warns when
      the task is below joblib's overhead threshold.
    script: scripts/recommend_params.py
    inputs:
      - name: task-type
        type: string
      - name: n-items
        type: integer
      - name: seconds-per-item
        type: float
      - name: progress-wanted
        type: boolean
    outputs:
      - name: params
        type: object
        description: >
          {n_jobs, backend, verbose, worth_parallelizing,
          estimated_sequential_seconds, warnings, snippet}.

  - name: decide-sequential-or-parallel
    description: >
      If params.worth_parallelizing is false, or n-items == 1, run the
      loop sequentially and stop — joblib overhead would dominate.
      Otherwise continue. Surface any warnings to the user.
    inputs:
      - name: params
        type: object
    one_of:
      - run-sequential-loop
      - proceed-with-parallel

  - name: define-worker-function
    description: >
      Write a top-level (picklable) function that takes one item and
      returns one result. Must not reference closures over large objects
      — pass shared data in explicitly (see next step). Return None on
      failure so callers can filter, or raise if a failure should abort
      the whole sweep.
    outputs:
      - name: worker-fn
        type: object
        description: Picklable callable, one item in / one result out.

  - name: precompute-shared-data
    description: >
      When every worker needs the same data (loaded dataset, lookup
      table, fitted model), compute it once outside the Parallel(...)
      call and pass it as an argument inside delayed(). Each worker gets
      a copy, so keep the payload small; for very large data prefer
      memory-mapped arrays or backend='loky' with a shared file.
    outputs:
      - name: shared-data
        type: object
        nullable: true

  - name: invoke-parallel
    description: >
      Call Parallel(**params)(delayed(worker_fn)(item, shared_data) for
      item in items). Results come back in input order. Use itertools
      .product when iterating a grid of parameter combinations.
    inputs:
      - name: params
        type: object
      - name: worker-fn
        type: object
      - name: shared-data
        type: object
        nullable: true
    outputs:
      - name: raw-results
        type: list[object]

  - name: aggregate-and-filter
    description: >
      Filter out None / failed results, then reduce (max-by-score,
      collect into a frame, etc.). The grid-search idiom is
      `[r for r in results if r is not None]` followed by
      `max(results, key=lambda x: x['score'])` or a Pareto-frontier scan.
    inputs:
      - name: raw-results
        type: list[object]
    outputs:
      - name: final-result
        type: object

scenarios:
  - need: Baseline parallel batch — squaring 100 integers across cores.
    action: |
      from joblib import Parallel, delayed
      def process_item(x):
          return x ** 2
      results = Parallel(n_jobs=-1)(
          delayed(process_item)(x) for x in range(100)
      )
    outcome: All cores used; results in input order.

  - need: >
      Grid search over a parameter cross-product, scoring each combo and
      picking the best.
    context: >
      Use itertools.product to enumerate the grid, return one dict per
      combo, filter Nones, then max-by-score.
    action: |
      from joblib import Parallel, delayed
      from itertools import product
      def evaluate_params(param_a, param_b):
          score = expensive_computation(param_a, param_b)
          return {'param_a': param_a, 'param_b': param_b, 'score': score}
      params = list(product([0.1, 0.5, 1.0], [10, 20, 30]))
      results = Parallel(n_jobs=-1, verbose=10)(
          delayed(evaluate_params)(a, b) for a, b in params
      )
      results = [r for r in results if r is not None]
      best = max(results, key=lambda x: x['score'])
    outcome: Best-scoring combo found in parallel.

  - need: Every worker needs the same loaded dataset.
    context: >
      Loading inside the worker would re-read on every call. Load once,
      pass as an argument inside delayed().
    action: |
      shared_data = load_data()
      def process_with_shared(params, data):
          return compute(params, data)
      results = Parallel(n_jobs=-1)(
          delayed(process_with_shared)(p, shared_data)
          for p in param_list
      )
    outcome: Data is loaded once; workers receive copies.

anti_patterns:
  - Parallelizing a loop where per-item work is < 0.1s — joblib's
    process-startup and serialization overhead will exceed savings.
  - Loading shared data inside the worker function instead of
    pre-computing it once and passing it in.
  - Ignoring memory pressure — each worker holds a copy of arguments, so
    a 2 GB DataFrame × 16 workers blows out RAM.
  - Using backend='threading' for CPU-bound numeric work — the GIL caps
    real parallelism. Use the default 'loky' (processes) instead.
  - Using backend='loky' for I/O-bound work where threading would avoid
    serialization cost.
  - Forgetting to filter None results before reducing (max / sort /
    frame construction will crash or silently mis-rank).
  - Defining the worker as a lambda or nested function — joblib needs
    picklable callables for the loky backend.
```
