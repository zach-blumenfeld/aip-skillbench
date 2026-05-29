# Transformation Patterns

Canonical before/after rewrites. Pick the pattern that matches the workload classification from `decision-tree.md`.

## Pattern 1: Loop to ProcessPoolExecutor (CPU-bound)

**Before:**
```python
results = []
for item in items:
    results.append(expensive_computation(item))
```

**After:**
```python
from concurrent.futures import ProcessPoolExecutor

with ProcessPoolExecutor() as executor:
    results = list(executor.map(expensive_computation, items))
```

## Pattern 2: Sequential I/O to Async (I/O-bound)

**Before:**
```python
import requests

def fetch_all(urls):
    return [requests.get(url).json() for url in urls]
```

**After:**
```python
import asyncio
import aiohttp

async def fetch_all(urls):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_one(session, url) for url in urls]
        return await asyncio.gather(*tasks)

async def fetch_one(session, url):
    async with session.get(url) as response:
        return await response.json()
```

## Pattern 3: Nested Loops to Vectorization

**Before:**
```python
result = []
for i in range(len(a)):
    row = []
    for j in range(len(b)):
        row.append(a[i] * b[j])
    result.append(row)
```

**After:**
```python
import numpy as np
result = np.outer(a, b)
```

## Pattern 4: Mixed CPU/IO with asyncio

```python
import asyncio
from concurrent.futures import ProcessPoolExecutor

async def hybrid_pipeline(data, urls):
    loop = asyncio.get_event_loop()

    # CPU-bound in process pool
    with ProcessPoolExecutor() as pool:
        processed = await loop.run_in_executor(pool, cpu_heavy_fn, data)

    # I/O-bound with async
    results = await asyncio.gather(*[fetch(url) for url in urls])

    return processed, results
```

## Pattern 5: Pool Initializer for Large Shared State (CPU-bound)

When every worker needs the same large read-only object (index, model, lookup table), pickling it on every call destroys speedup. Load it once per worker via `Pool`'s `initializer`/`initargs`, stash it in module globals, and pass only the per-call input.

```python
import multiprocessing as mp
from multiprocessing import Pool

# Module-level worker state — populated by the initializer
_worker_state = None

def _init_worker(big_shared_object):
    global _worker_state
    _worker_state = big_shared_object

def _do_work(task_input):
    global _worker_state
    # Use _worker_state freely; no IPC cost per call
    return process(_worker_state, task_input)

def run_batch(tasks, big_shared_object, num_workers=None):
    num_workers = num_workers or mp.cpu_count()
    with Pool(
        processes=num_workers,
        initializer=_init_worker,
        initargs=(big_shared_object,),
    ) as pool:
        return pool.map(_do_work, tasks, chunksize=max(1, len(tasks) // (num_workers * 4)))
```

Use this whenever the per-call payload (query, item id, batch index) is small but the shared context (index, model) is large.

## Pattern 6: MapReduce over Document Batches (CPU-bound)

For tasks that need a global aggregate computed from per-item local results (vocabularies, document frequencies, partial inverted indexes), split into three phases:

1. **Map** — each worker processes a batch of items and returns *only* the aggregated structures (per-doc TF dicts, term sets, local vocabulary). Avoid returning the raw inputs.
2. **Reduce** — single-threaded merge of the per-worker dicts/sets to compute global state (document frequency, IDF).
3. **Map again** — each worker uses the global state (small, broadcast as args) to build a partition of the final structure (inverted index shard, doc vectors), which is then merged sequentially.

Pseudocode:

```python
from multiprocessing import Pool

def map_batch(batch):
    # tokenize + per-doc TF; return aggregated per-batch dicts
    ...

def map_partition(args):
    batch_tf, global_idf, n_docs = args
    # build inverted-index shard + doc vectors for this partition
    ...

def parallel_build(items, num_workers, chunk_size=500):
    batches = [items[i:i+chunk_size] for i in range(0, len(items), chunk_size)]

    with Pool(num_workers) as pool:
        partials = pool.map(map_batch, batches)

    # Reduce — fast, sequential
    global_tf, global_terms = merge(partials)
    global_df = compute_df(global_terms)
    global_idf = compute_idf(global_df, n_docs=len(items))

    # Second map — partition by doc id, build inverted-index shards
    partitions = partition(global_tf, num_workers)
    args = [(p, global_idf, len(items)) for p in partitions]
    with Pool(num_workers) as pool:
        shards = pool.map(map_partition, args)

    return merge_shards(shards)
```

This is the pattern the curated TF-IDF benchmark expects — see `source/SKILL.md` and the oracle solution for the concrete instantiation.

## Pickling-Safe Worker Functions

`multiprocessing` pickles worker functions to ship them to children. To avoid `PicklingError`:

- Define worker functions at **module top level** — not nested inside another function or class.
- Pass plain data (tuples, dicts of primitives) as arguments — not closures, lambdas, or custom objects with `__getstate__` quirks.
- If you must share large state, prefer the **initializer pattern (Pattern 5)** over pickling on each call.
