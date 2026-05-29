# Parallelization Decision Tree

Pick the parallelization primitive by workload type. CPU/I/O classification first, then drill into the indicators.

```
Is the bottleneck CPU-bound or I/O-bound?

CPU-bound (computation-heavy):
├── Independent iterations? → multiprocessing.Pool / ProcessPoolExecutor
├── Shared state needed? → multiprocessing with Manager or shared memory
├── NumPy/Pandas operations? → Vectorization first, then consider numba/dask
└── Large data chunks? → chunked processing with Pool.map

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

## Parallelization Candidates

Look for these patterns in the source code:

| Pattern | Indicator | Strategy |
|---------|-----------|----------|
| `for item in collection` with independent iterations | No shared mutation | `Pool.map` / `executor.map` |
| Multiple `requests.get()` or file reads | Sequential I/O | `asyncio.gather()` |
| Nested loops over arrays | Numerical computation | NumPy vectorization |
| `time.sleep()` or blocking waits | Waiting on external | Threading or async |
| Large list comprehensions | Independent transforms | `Pool.map` with chunking |

## Classification Heuristics

- **CPU-bound** — function spends time on math, tokenization, regex, encoding, compression, ML inference, or any pure-Python computation. `top` shows the process pinned at 100% of one core.
- **I/O-bound** — function spends time waiting on sockets, disk, or DBs. `top` shows the process idle or low CPU while wall-clock grows.
- **Data-parallel** — the work is element-wise math over arrays/matrices. Replacing Python loops with `numpy` vectorized ops often beats any process-pool approach.

## TF-IDF Indexing & Search — Classification

TF-IDF index construction is **CPU-bound, embarrassingly parallel** over documents:

- Tokenization, term-frequency counting, and per-document TF-IDF vector building have no cross-document dependencies → `multiprocessing.Pool` with `Pool.map` over document batches.
- The GIL blocks `threading` from helping — use processes.
- Document-frequency aggregation and IDF computation must run **once** after the per-document phase; they are fast and sequential.

Batch search over many independent queries is also CPU-bound and embarrassingly parallel:

- Each query independently looks up postings, computes cosine similarity, and selects top-k → `Pool.map` over queries.
- The index is large and identical for every query — use a worker-pool **initializer** to load it once per worker rather than pickling it on every call. See `references/transformation-patterns.md` § Pattern 5.
