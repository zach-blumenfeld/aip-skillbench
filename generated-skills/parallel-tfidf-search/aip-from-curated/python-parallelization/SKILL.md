---
name: python-parallelization
description: Transform sequential Python code into parallel/concurrent implementations. Use when asked to parallelize Python code, improve code performance through concurrency, convert loops to parallel execution, or identify parallelization opportunities. Handles CPU-bound (multiprocessing), I/O-bound (asyncio, threading), and data-parallel (vectorization) scenarios. Includes a verification script that compares correctness and speedup against a sequential baseline.
license: Proprietary. LICENSE.txt has complete terms
compatibility: Requires Python 3.10+. Standard library only for the core procedure; aiohttp/numpy/numba/dask/cupy/jax are optional and only invoked when the corresponding strategy is selected.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Transform sequential Python into parallel implementations that are
  correct and faster on multi-core systems. Classify the workload
  (CPU-bound, I/O-bound, or data-parallel), pick the right primitive
  (multiprocessing / asyncio / threading / vectorization), apply a
  canonical transformation pattern, and verify correctness + speedup
  against the sequential baseline before declaring done.

trigger_when:
  - User asks to parallelize Python code or to convert sequential loops to parallel execution.
  - User asks to improve performance via concurrency or to identify parallelization opportunities.
  - A task supplies a sequential baseline plus a speedup target (e.g., "1.5x indexing, 2x batch search with 4 workers").
  - A test suite measures wall-clock against a sequential implementation.
  - The user mentions multiprocessing, multithreading, asyncio, vectorization, or "use all CPU cores".

do_not_use_when:
  - The bottleneck is algorithmic complexity — switching algorithms fixes it more cleanly than parallelizing.
  - The input is small enough that parallel overhead exceeds the gain (typically < 1000 items or < 1 ms per item).
  - Correctness depends on strict sequential ordering that cannot be preserved by a parallel reduction.

scope_and_approval: >
  Write the parallel implementation to the file path the task specifies
  (e.g., `/root/workspace/parallel_solution.py` in the curated TF-IDF
  benchmark). Do not modify the sequential baseline, fixtures, or shared
  data classes — the verifier imports and compares against them. Keep
  every worker function at module top level so multiprocessing can pickle
  it. Bound worker counts (default `cpu_count()`, honor explicit
  task-supplied counts in tests). No network or filesystem writes outside
  the declared output file.

steps:
  - name: analyze-code
    description: >
      Read the sequential baseline end-to-end. Identify loops/comprehensions
      whose iterations are independent (no cross-iteration writes),
      large reductions, and any cross-iteration dependencies that would
      block parallelization. List candidate hotspots before picking a
      strategy. See `references/decision-tree.md` § Parallelization
      Candidates for the indicator table.
    outputs:
      - name: candidates
        type: list[object]
        description: Hotspots with location, indicator, and likely strategy.

  - name: classify-workload
    description: >
      Tag each candidate as CPU-bound, I/O-bound, or data-parallel using
      the heuristics in `references/decision-tree.md`. The choice of
      primitive (multiprocessing vs asyncio vs vectorization) follows
      directly. For the curated TF-IDF task, indexing and batch search are
      both CPU-bound and embarrassingly parallel over documents/queries.
    inputs:
      - name: candidates
        type: list[object]
    outputs:
      - name: classified-candidates
        type: list[object]
    one_of:
      - CPU-bound — pure-Python computation, regex, math; one core at 100%. Use multiprocessing.
      - I/O-bound — network/disk/db waits; low CPU during work. Use asyncio (or ThreadPoolExecutor for legacy sync).
      - Data-parallel — elementwise math over arrays/matrices. Use NumPy/Pandas vectorization first.

  - name: select-strategy
    description: >
      Pick one transformation pattern per candidate from
      `references/transformation-patterns.md`. For TF-IDF index build,
      Pattern 6 (MapReduce over document batches) is the expected shape.
      For TF-IDF batch search, Pattern 5 (Pool initializer for large
      shared state) is critical — pickling the index per query destroys
      speedup; load it once per worker.
    inputs:
      - name: classified-candidates
        type: list[object]
    outputs:
      - name: strategy-plan
        type: list[object]
    one_of:
      - Pattern 1 — Loop → ProcessPoolExecutor (CPU, independent iterations).
      - Pattern 2 — Sequential I/O → asyncio.gather (I/O-bound, many requests).
      - Pattern 3 — Nested numeric loops → NumPy vectorization (data-parallel).
      - Pattern 4 — Mixed CPU+IO → asyncio with run_in_executor for the CPU stage.
      - Pattern 5 — Pool initializer for large read-only shared state (preload once per worker).
      - Pattern 6 — MapReduce over batches (per-doc map → global reduce → per-shard map).

  - name: transform
    description: >
      Implement the parallel version at the file path the task specifies.
      Module-top-level worker functions; pass primitives (tuples of ids,
      dicts of floats) rather than rich objects; bound worker count to
      `num_workers or mp.cpu_count()`; use context managers for every
      Pool/Executor. For the curated TF-IDF task, expose
      `build_tfidf_index_parallel(documents, num_workers=None,
      chunk_size=500)` returning a `ParallelIndexingResult` (with the same
      `TFIDFIndex` structure as `sequential.py`) and
      `batch_search_parallel(queries, index, top_k=10, num_workers=None,
      documents=None)` returning `(List[List[SearchResult]],
      elapsed_time)`.
    inputs:
      - name: strategy-plan
        type: list[object]
    outputs:
      - name: parallel-source-path
        type: string

  - name: verify
    description: >
      Run the bundled verifier to confirm correctness and speedup against
      the sequential baseline. Fails fast (exit 1) on IDF mismatch, search
      mismatch, or under-target speedup; JSON-Lines diagnostics on stderr
      tell you which dimension failed. Iterate on transform until all
      three checks pass on the task's hardware. Override defaults
      (`--num-workers`, `--index-speedup`, `--search-speedup`) only if the
      task specifies different targets.
    script: scripts/verify_parallel.py
    depends_on: [transform]
    inputs:
      - name: parallel-source-path
        type: string
    outputs:
      - name: verification-report
        type: object
        description: stdout summary line + JSONL diagnostics on stderr.

search_shortcuts:
  - category: CPU-bound primitives
    body: >
      `concurrent.futures.ProcessPoolExecutor`, `multiprocessing.Pool`
      (with `initializer`/`initargs` for large shared state),
      `multiprocessing.Manager` (shared dict/list with lock overhead).
      Prefer Pool over ProcessPoolExecutor when the initializer pattern
      matters — ProcessPoolExecutor does not expose one directly.
  - category: I/O-bound primitives
    body: >
      `asyncio` + `aiohttp` / `aiofiles` / `asyncpg`,
      `concurrent.futures.ThreadPoolExecutor` for legacy sync I/O,
      `asyncio.to_thread` / `loop.run_in_executor` to bridge sync into async.
  - category: Data-parallel primitives
    body: >
      NumPy vectorized ops (`np.outer`, `np.dot`, broadcasting), Pandas
      vectorized methods, `numba.njit(parallel=True)`, Dask for
      out-of-core, CuPy / JAX when a GPU is available.

scenarios:
  - need: >
      Curated parallel-TF-IDF benchmark. `sequential.py` ships
      `build_tfidf_index_sequential` and `batch_search_sequential`; the
      verifier requires 1.5x index-build speedup and 2x batch-search
      speedup with 4 workers, and bit-for-bit (within 1e-6) result
      equivalence.
    context: >
      8-core container; documents/queries are independent;
      `Document`/`TFIDFIndex`/`SearchResult` dataclasses must be reused
      verbatim so the verifier's `isinstance`/attribute checks pass.
    action: >
      Pattern 6 for index build (process_document_batch → reduce to
      DF/IDF → build_partial_index → merge inverted index, sorting
      postings descending by score). Pattern 5 for batch search
      (`Pool(initializer=_init_search_worker, initargs=(...))` loads the
      index into worker globals; worker fn takes only the query string;
      `chunksize=max(1, len(queries) // (num_workers * 4))`). Fall back
      to `batch_search_sequential` when `len(queries) < num_workers * 2`
      to avoid overhead-dominated runs. Then
      `python scripts/verify_parallel.py --workspace /root/workspace
      --parallel-module parallel_solution --num-workers 4`.
    outcome: >
      Verifier prints
      `correctness=idf:ok search:ok index_speedup=≥1.5x search_speedup=≥2x`;
      pytest in tests/ passes.

  - need: User asks "speed up this script that downloads 500 URLs sequentially with requests."
    context: I/O-bound; each `requests.get` blocks on the network.
    action: >
      Classify as I/O-bound; apply Pattern 2. Rewrite as `async def
      fetch_one` with `aiohttp.ClientSession` and `asyncio.gather`. Wrap
      the entry point in `asyncio.run`. No multiprocessing needed.
    outcome: 10–50× wall-clock improvement depending on per-request latency.

  - need: User asks to speed up a triple-nested loop computing pairwise products of two 10k-element arrays.
    context: Data-parallel numeric work.
    action: >
      Classify as data-parallel; apply Pattern 3. Replace the loop with
      `np.outer(a, b)` (or `a[:, None] * b[None, :]`). Skip
      multiprocessing entirely — vectorization beats it for pure-numeric
      work.
    outcome: 100×+ speedup; multiprocessing would have added overhead and underperformed.

anti_patterns:
  - Threading a CPU-bound pure-Python workload — the GIL serializes execution; use multiprocessing or vectorization instead.
  - Defining worker functions inside another function, a class, or as lambdas — multiprocessing fails to pickle them at submit time.
  - Passing the full index/corpus as a per-call argument to a worker pool — IPC cost dwarfs the work; use the Pool initializer pattern to preload large read-only state once per worker.
  - Sprinkling `async`/`await` onto an otherwise sync codebase without restructuring the call chain — most call sites still block, so wall-clock does not improve.
  - Spawning a worker per item — fork/pickle overhead eats the gain; chunk the work (~4× as many chunks as workers).
  - Ignoring sequential fallback for small inputs — for the curated TF-IDF batch search the oracle falls back to `batch_search_sequential` when `len(queries) < num_workers * 2`. Without it, micro-batches run slower than sequential.
  - Comparing parallel and sequential results with strict equality — parallel reductions reorder float adds; use `abs(a - b) < 1e-6` or sort by `(-score, doc_id)` before comparing ranked lists.
  - Forgetting to sort posting lists by score after merging shards — the sequential baseline returns sorted postings; an unsorted merged list breaks any caller that relies on order.
  - "Hard-coding `num_workers=4` in the production signature — accept `num_workers: Optional[int] = None`, default to `mp.cpu_count()`, and honor the explicit value only when the caller (or test) supplies it."
```
