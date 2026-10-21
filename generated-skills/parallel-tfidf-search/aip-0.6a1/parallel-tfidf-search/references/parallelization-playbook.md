# Parallelizing the TF-IDF engine: playbook

Compiled from the python-parallelization, workload-balancing and memory-optimization
skills (originals in `source/`), applied to `sequential.py` / `parallel_solution.py`.

## 1. Exactness invariants (results must be identical, not approximately equal)

The checker compares the parallel index and search results to the sequential ones with `==`.
Floating-point sums depend on order, and dataclass `__eq__` depends on the class object.

| Invariant | Why | How the template keeps it |
|---|---|---|
| Import `TFIDFIndex`, `SearchResult`, `IndexingResult` from `sequential` | dataclass `__eq__` returns `NotImplemented` across different classes, so a copy-pasted class never compares equal | `from sequential import ...`; `ParallelIndexingResult(IndexingResult)` |
| Reuse `tokenize` and `compute_term_frequencies` | same tokens, same TF floats, same dict insertion order | imported, called in workers |
| Merge per-document results in original document order | posting lists are filled in doc order before a *stable* sort; ties keep doc order | `pool.imap` (ordered), never `imap_unordered`/`as_completed` for the merge |
| `tfidf = tf * idf[term]`, `idf = math.log(N / df) + 1`, `N = len(documents)` | identical arithmetic expression gives identical float | same expressions |
| Norm: `sum(tfidf*tfidf)` in TF-dict order, then `math.sqrt` | float addition is not associative | loop over `tf_dict.items()` in its own order |
| Duplicate `doc_id`s: last TF wins but the dict keeps first position; `N` still counts every document | baseline stores into a dict keyed by doc_id | merge into a dict in doc order; recompute DF from the merged dict when ids are not unique |
| Search dot products: builtin `sum()` over `q_weight * d_weight` in query-term order | Python 3.12+ `sum()` of floats is compensated (Neumaier); a hand-rolled `acc += x` differs in the last bit. Absent terms only add `0.0`, so summing just the present products is identical | `_score_query` collects products per doc from the posting lists (posting weights are the same `tf * idf` floats as `doc_vectors`) and calls `sum(list)` |
| Search tie order | `nlargest` keeps the first of equal scores in candidate-set iteration order, which depends on set insertion order | candidate set filled in the baseline's order (query terms in order, posting lists in order); same `nlargest(top_k, scores, key=score)`; parent attaches titles with the same `doc_titles.get(doc_id, f"Document {doc_id}")` rule |
| Fallback when the baseline's search differs | any other formula changes floats or ties | call the baseline's own `search_sequential(q, index, top_k, None)` in workers and keep only `(doc_id, score)` |
| Return types | `build_tfidf_index_parallel` → `ParallelIndexingResult` (`.index`, `.elapsed_time`, `.num_documents`, `.vocabulary_size`); `batch_search_parallel` → `(List[List[SearchResult]], elapsed_time)` | as written |

## 2. Where the time goes (5,000-doc corpus, ~2.8M words)

- Index: tokenizing (`re.findall` + stop-word filter) and TF counting dominate and are
  independent per document → map them over a process pool. The baseline's DF and
  posting steps scan vocabulary × documents; a single pass over the TF dicts in the
  parent replaces them (same results, far less work).
- Search: each query scores every candidate document, probing each candidate's dict once per
  query term; queries are independent → split queries across workers, and score from the
  posting lists (≈2.8x less work per query, identical floats). The baseline rebuilds the title
  map per query; build it once.
- Pool start-up costs ~40–50 ms per call (fork of a process holding the index), so tiny
  batches cannot reach 2x by parallelism alone; the cheaper per-query scoring is what keeps
  small batches above target.

## 3. Choosing the parallel strategy (python-parallelization)

Decision tree:
```
CPU-bound (computation-heavy):
├── Independent iterations? → multiprocessing.Pool / ProcessPoolExecutor      ← this task
├── Shared state needed? → multiprocessing with Manager or shared memory
├── NumPy/Pandas operations? → Vectorization first, then consider numba/dask
└── Large data chunks? → chunked processing with Pool.map                     ← this task
I/O-bound (network, disk, database):
├── Many independent requests? → asyncio with aiohttp/aiofiles
├── Legacy sync code? → ThreadPoolExecutor
├── Mixed sync/async? → asyncio.to_thread()
└── Database queries? → Connection pooling + async drivers
Data-parallel (array/matrix ops):
├── NumPy arrays? → Vectorize, avoid Python loops
├── Pandas DataFrames? → Use built-in vectorized methods
├── Large datasets? → Dask for out-of-core parallelism
└── GPU available? → Consider CuPy or JAX
```
Candidates: `for item in collection` with no shared mutation → `Pool.map`; large
independent list comprehensions → `Pool.map` with chunking; nested numeric loops →
vectorize; sequential I/O → `asyncio.gather()`; blocking waits → threads/async.

Pitfalls:
- **GIL trap**: threads do not speed up CPU-bound Python; use processes.
- **Pickle failures**: lambdas, nested functions and nested classes cannot be sent to
  workers; worker functions must be module-level.
- **Memory explosion**: each task's arguments are pickled to the worker. Do not pass the
  index or the document list per task; publish it in a module global before forking
  (copy-on-write inheritance), or send it once through `Pool(initializer=...)` under spawn.
- **Over-parallelization**: pool start-up and IPC cost more than they save on tiny inputs
  (<~1000 items); fall back to in-process work for 1 worker or a single chunk.
- **Async in sync**: adding `async` is not a speedup for CPU work and needs a restructured call chain.

Safety: identify shared state; iteration N must not depend on N-1; handle exceptions
(`try/finally` around the pool, `submit()` for per-item errors); bound the worker count
(`num_workers=None` → `os.cpu_count()`); preserve order with `map`/`imap` rather than
`submit` + `as_completed` when order matters.

Start methods: Linux before Python 3.14 defaults to `fork` (the container: python:3.12-slim);
macOS and 3.14+ default to `spawn`/`forkserver`. Ask for `mp.get_context("fork")` when
available, keep the spawn path working via an initializer. Under spawn, worker functions are
re-imported by module name, so the solution file must be importable from its folder.

## 4. Balancing the work (workload-balancing)

Document lengths are log-normal (20–2,000+ words): a long-tail, variable workload.
```
Uniform task times:   known count → static equal chunks; streaming → round-robin; large items → size-aware
Variable task times:  predictable → weighted distribution; unpredictable → dynamic scheduling / work stealing;
                      long tail → work stealing + time limits
Resource constraints: memory-bound → memory-aware assignment; heterogeneous → capability routing;
                      network costs → locality-aware placement
```
- Use many contiguous chunks (index: `chunk_size` docs, default 500; search: ~4 chunks per
  worker) pulled dynamically by `imap`: idle workers take the next chunk, so a chunk of long
  documents does not create a straggler, and contiguous ranges keep the merge order.
- Weighted (greedy largest-first bin packing by word count) is the alternative when chunks
  are few; it breaks document order, so re-sort results by original position before merging.
- Over-partitioning (tiny chunks) adds IPC overhead; batch small items.
- Targets to check if speedup is low: load imbalance `max(load)/avg(load)` < 1.2,
  straggler ratio `max(time)/median(time)` < 2.0, worker utilization `busy/total` > 90%,
  queue-depth variance `std(queue_lengths)` low.
- Balancing anti-patterns: starvation (large tasks block the queue → break into subtasks),
  thundering herd (all workers wake at once → jitter), hot spots (uneven key distribution →
  better hash), convoy effect (workers wait on one resource → finer-grained locking),
  over-partitioning (too many small tasks → batch small items).
- Workflow: characterize task times → find stragglers/uneven distribution → pick the strategy →
  implement partitioning → measure completion times and adapt.
- Partitioning menu: equal chunks (`np.array_split` / slices), round-robin (`items[i::n]`),
  size-weighted (bin packing), hash-based (`hash(key) % n`), range-based (contiguous ranges).
- Stragglers: timeouts with fallback, speculative backup tasks, dynamic rebalancing; not needed
  here once chunks are dynamic.

## 5. Memory (memory-optimization)

Workflow: profile → analyze structures and lifetimes → pick a strategy by access pattern →
transform → verify memory dropped and output unchanged.
```
Large collections:  list of objects → __slots__ / namedtuple / dataclass(slots=True);
                    list built all at once → generator; repeated strings → sys.intern / categorical;
                    numeric data → NumPy arrays (not in this container)
Data processing:    full file load → chunked reading / mmap; intermediate copies → in-place ops, views;
                    keeping processed data → process-and-discard; DataFrames → downcast dtypes, sparse
Object lifecycle:   never freed → circular refs, weakref; unbounded cache → lru_cache(maxsize=...);
                    global accumulation → explicit cleanup, context managers;
                    large temporaries → del + gc.collect()
```
Rough per-item cost: list of dict ~400+ B, list of class ~300 B, `__slots__` class ~120 B,
namedtuple ~80 B, numpy float64 8 B, DataFrame cell ~10–50 B.
Leaks: growing cache (no eviction → `lru_cache(maxsize=1000)`), unregistered listeners (weakrefs),
reference cycles (`weakref`, break cycles), global lists (bounded `deque`, periodic clear),
closures capturing large objects (capture only what is needed). In this task the module
globals holding documents/index are reset to `None` after each call for that reason.

- Workers return only what the parent needs: `(doc_id, tf_dict)` and partial DF counters
  for indexing; `(doc_id, score)` pairs for search — not `SearchResult` objects or titles.
- `gc.freeze()` before forking keeps inherited objects out of GC passes so their pages stay
  shared; `gc.unfreeze()` after the pool closes.
- Process-and-discard: drop chunk results (`del parts`) once merged; reset globals after use.
- Generators/chunking over materialized lists; `"".join` over `+=`; `__slots__`/namedtuples
  for many small records; `sys.intern` for repeated strings — only if memory is the bottleneck.
- Measure with `tracemalloc` (`tracemalloc.start()`, `take_snapshot().statistics('lineno')`),
  `sys.getsizeof` (shallow), `pympler.asizeof` (deep, not installed in the container).

## 6. Verification checklist (all three skills)

- [ ] Output identical to the sequential version (index fields and search results with `==`)
- [ ] No race conditions; no shared mutable state written by workers
- [ ] Exceptions handled; pools terminated and joined in `finally`
- [ ] Worker count bounded; defaults match the required signatures
- [ ] Work evenly distributed (no straggler chunk); overhead acceptable vs task cost
- [ ] Memory reasonable (no per-task copies of the index); no leaks across calls
- [ ] Needed imports present; only stdlib (the container has no numpy)
