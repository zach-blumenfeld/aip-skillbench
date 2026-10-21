# Parallelization, load-balancing and memory playbook

Condensed from the source skills (python-parallelization, workload-balancing,
memory-optimization; verbatim originals under `source/`). Load this when you have to
adapt the template to a baseline that differs, or when a speedup target is missed.

## 1. Workflow (all three sources merged)

1. **Profile / analyze**: find the hot loops (time each baseline step; `tracemalloc`
   or `sys.getsizeof` for memory).
2. **Classify** the workload: CPU-bound, I/O-bound, or data-parallel.
3. **Characterize** task times: uniform vs variable (TF-IDF docs are log-normal:
   variable, long tail).
4. **Select** strategy (trees below), **transform** with proper synchronization and
   error handling, **implement** partitioning/scheduling.
5. **Verify** identical output, measure speedup and memory; **monitor** balance.

## 2. Parallelization decision tree

```
CPU-bound (computation-heavy):
├── Independent iterations? → multiprocessing.Pool / ProcessPoolExecutor
├── Shared state needed?    → multiprocessing with Manager or shared memory
├── NumPy/Pandas operations? → vectorize first, then numba/dask
└── Large data chunks?      → chunked processing with Pool.map
I/O-bound (network, disk, database):
├── Many independent requests? → asyncio with aiohttp/aiofiles
├── Legacy sync code?          → ThreadPoolExecutor
├── Mixed sync/async?          → asyncio.to_thread()
└── Database queries?          → connection pooling + async drivers
Data-parallel (array/matrix ops):
├── NumPy arrays? → vectorize, avoid Python loops
├── Pandas?       → built-in vectorized methods
├── Larger than RAM? → Dask out-of-core
└── GPU?          → CuPy or JAX
```
TF-IDF tokenizing/scoring is pure-Python CPU-bound with independent iterations →
process pool. (The task container is `python:3.12-slim`: no numpy/numba/dask.)

### Candidate patterns to look for

| Pattern | Indicator | Strategy |
|---|---|---|
| `for item in collection`, independent iterations | no shared mutation | `Pool.map` / `executor.map` |
| many `requests.get()` / file reads | sequential I/O | `asyncio.gather()` |
| nested loops over arrays | numeric | NumPy vectorization (`np.outer` etc.) |
| `time.sleep()` / blocking waits | waiting on external | threads or async |
| large list comprehensions | independent transforms | `Pool.map` with chunking |

Loop → pool: `with ProcessPoolExecutor() as ex: results = list(ex.map(fn, items))`.
Mixed CPU/IO: `await loop.run_in_executor(process_pool, cpu_fn, data)` plus
`asyncio.gather` for the I/O.

### Safety requirements

1. Identify shared state: variables mutated across iterations break parallelism.
2. Check dependencies: iteration N needing N-1 must stay sequential (here: IDF needs
   all document frequencies, so it is a reduce step after the parallel map).
3. Handle exceptions: `executor.submit()` + `as_completed` for per-item errors;
   `asyncio.gather(..., return_exceptions=True)` for async.
4. Manage resources: context managers; bound the worker count.
5. Preserve ordering: `map()`/`imap()` over `submit()`/`imap_unordered` when order matters.

### Common pitfalls

- **GIL trap**: threads do not speed up CPU-bound Python; use processes.
- **Pickle failures**: lambdas, nested functions/classes cannot be sent to workers;
  worker functions must be module-level.
- **Memory explosion**: each process gets a copy of what you send; use fork
  inheritance or shared memory for large read-only data.
- **Async in sync**: adding `async` needs the whole call chain restructured.
- **Over-parallelization**: overhead beats gains for small workloads (the source rule
  of thumb is <1000 items; for whole TF-IDF documents measured break-even is ~64 docs
  with fork, a few queries for search).

## 3. Load-balancing decision tree

```
Uniform task times:  known count → static equal chunks; streaming → round-robin;
                     large items → size-aware partitioning
Variable task times: predictable variance → weighted distribution;
                     unpredictable → dynamic scheduling / work stealing;
                     long tail → work stealing + time limits
Resource constraints: memory-bound → memory-aware assignment;
                     heterogeneous workers → capability routing; network → locality
```

Strategies:
1. **Static chunking** (uniform): `np.array_split(items, n)` / equal slices, one per worker.
2. **Dynamic task queue** (variable): many small tasks pulled as workers free up,
   e.g. `Pool.imap(fn, chunks)` or submit-on-completion with `wait(FIRST_COMPLETED)`.
3. **Work stealing** (long tail): per-worker deques, idle workers steal from the busiest.
4. **Weighted distribution** (known costs, e.g. document length): sort by weight
   descending, assign each to the least-loaded worker (LPT bin packing). If you use
   this, re-sort results back to original document order before assembling.
5. **Semaphore** (I/O): cap concurrent operations.

| Partitioning | Best for | Implementation |
|---|---|---|
| Equal chunks | uniform tasks | `np.array_split(items, n)` |
| Round-robin | streaming | `items[i::n_workers]` |
| Size-weighted | known sizes | bin packing |
| Hash-based | consistent routing | `hash(key) % n_workers` |
| Range-based | sorted data | contiguous ranges |

Stragglers: timeout with fallback (`future.result(timeout=...)`), speculative backup
tasks, or dynamic rebalancing when a task runs > 2x the mean.

### Monitoring targets (use when diagnosing a missed speedup)

| Metric | Calculation | Target |
|---|---|---|
| Load imbalance | `max(load) / avg(load)` | < 1.2 |
| Straggler ratio | `max(time) / median(time)` | < 2.0 |
| Worker utilization | `busy_time / total_time` | > 90% |
| Queue depth variance | `std(queue_lengths)` | low |

Anti-patterns: starvation (large tasks block queue → split them), thundering herd
(jitter), hot spots (better hash), convoy on one resource (finer locks),
over-partitioning (too many tiny tasks → batch them).

## 4. Memory techniques relevant to parallel Python

```
Large collections: many objects → __slots__/namedtuple/dataclass(slots=True);
                   built all at once → generators; repeated strings → sys.intern /
                   categorical; numeric → arrays
Data processing:   whole file → chunked reads / mmap; intermediate copies → in-place,
                   views; keep-everything → process-and-discard
Object lifecycle:  never freed → circular refs/weakref; unbounded cache → lru_cache(maxsize);
                   global accumulation → explicit cleanup; big temporaries → del + gc.collect()
```

- Send workers the minimum: `(doc_id, title, content)` tuples, not Document objects or
  the index per task; return only what the reduce step needs (term-frequency dicts).
- Read-only big structures (the index): fork inheritance (copy-on-write) on Linux;
  otherwise pickle **once** to bytes and pass via the pool initializer, or
  `multiprocessing.shared_memory` for flat numeric arrays.
- Join strings with `"".join(...)`, not `+=` in loops.
- `__slots__` cuts per-instance memory ~40–60%; downcasting NumPy/Pandas dtypes saves 2–8x;
  `mmap` / `np.memmap` and chunked `pd.read_csv(chunksize=...)` (with `del chunk`) handle
  files larger than RAM.
- Approximate per-item cost: list of dict ~400+ B, class ~300 B, `__slots__` ~120 B,
  namedtuple ~80 B, float64 array 8 B.
- Leak patterns: growing cache (add maxsize), unregistered listeners, cycles (weakref),
  global lists (bounded deque), closures capturing big objects.
- Profiling: `sys.getsizeof` (shallow), `pympler.asizeof` (deep, not installed in the
  container), `tracemalloc.start(); snapshot.statistics('lineno')`.

## 5. Verification checklists (merged)

- [ ] Output matches the sequential version exactly (run `scripts/verify_parallel.py`)
- [ ] No race conditions; no shared mutable state written by workers
- [ ] Exceptions surface (a worker exception re-raises in the parent through `imap`)
- [ ] Pools closed (context manager), worker count bounded
- [ ] Work evenly distributed, no starvation, stragglers bounded
- [ ] Overhead acceptable vs task cost (small inputs run in-process)
- [ ] Memory: nothing large copied per task; no new leaks
- [ ] Imports added; code readable

## 6. Advanced patterns (from the sources' `references/advanced_techniques.md`)

Full code is in `source/*/references/advanced_techniques.md`; open it only if you
adopt one of these.

| Pattern | Use when | Key detail |
|---|---|---|
| MapReduce shuffle | build steps that group by key (the TF-IDF index is map → reduce) | map emits `(key, value)`, partition by `hash(key) % num_reducers`, group then reduce per key; parallelize the reduce by term partition only if the merge step dominates |
| Shared-memory numpy array | large numeric arrays to workers | `shared_memory.SharedMemory(create=True, size=a.nbytes)`; workers attach by name, `close()` after use |
| Chunked processing | bound memory on huge inputs | `islice` chunks of `chunk_size` fed to `executor.map` |
| Progress with tqdm | long runs | `tqdm(as_completed(futures), total=...)` (tqdm not in the container) |
| Robust parallel processing | keep going on per-item errors | `submit` + `as_completed`, collect `(item, str(e))` errors |
| Async semaphore / rate limit | I/O fan-out | `asyncio.Semaphore(max_concurrent)`; `gather(..., return_exceptions=True)` |
| Producer–consumer queue | streaming async work | `asyncio.Queue`, one `None` poison pill per consumer |
| ThreadPool for blocking libs | no async alternative | `loop.run_in_executor(ThreadPoolExecutor(10), fn, item)` |
| Numba `@jit(nopython=True, parallel=True)` + `prange` | numeric loops that will not vectorize | needs numba (not in the container) |
| Dask | larger-than-memory frames/arrays | `dd.read_csv(...).groupby(...).compute()` |
| Consistent hashing | routing keys to nodes with minimal reshuffle on scaling | ring of md5 hashes, 100 virtual nodes per node, `bisect_right` |
| Rate-limited queue with backpressure | protect downstream services | sliding window of timestamps; wait until oldest expires |
| Priority balancer | mixed-priority tasks | heap per worker, submit to least-loaded by estimated cost |
| Circuit breaker | cascading failures | open after 5 failures, half-open after 30 s, close on success |
| Adaptive batch sizing | unknown optimal chunk size | start 100 (min 10, max 10000); throughput > 1.1x last → double, < 0.9x → halve |
| Locality-aware scheduling | workers with cached data | score = cache_hits*10 − load, pick max |
| Exponential backoff with full jitter | retries | delay = base*2^attempt, sleep `uniform(0, delay)`, max 5 tries |
| Object pool / flyweight / weak-value cache | many short-lived or duplicate heavy objects | reuse instances; `weakref.WeakValueDictionary` cache does not pin memory |
| Copy-on-write wrapper | share data until a writer appears | copy on first mutation |
| Struct-of-arrays, sparse matrices (`scipy.sparse` dok→csr) | numeric records / mostly-zero matrices | needs numpy/scipy (not in the container) |
| Pandas downcast / category | DataFrames | `pd.to_numeric(downcast=...)`; category if < 50% unique; `Int64` for integer floats with NaN |
| `memory_scope()` context manager | guarantee cleanup | `gc.collect()` in `finally` |
| Streaming JSON (`ijson.items(f, 'records.item')`) | huge JSON corpora | ijson not in the container; `load_corpus` reads whole files |
| String building | concatenating many pieces | `"".join(chunks)` or `io.StringIO`, never `+=` in a loop |
