# Parallel execution patterns

Code patterns for the executor named in `plan.executor`. Sections 1-4 come from the python-parallelization skill; the rest are its advanced techniques. All code is illustrative: replace `expensive_computation`, `process_item`, `fetch`, etc. with the target's functions.

## Transformation Patterns

### Pattern 1: Loop to ProcessPoolExecutor (CPU-bound)

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

### Pattern 2: Sequential I/O to Async (I/O-bound)

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

### Pattern 3: Nested Loops to Vectorization

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

### Pattern 4: Mixed CPU/IO with asyncio

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

## Parallelization Candidates

Look for these patterns in code:

| Pattern | Indicator | Strategy |
|---------|-----------|----------|
| `for item in collection` with independent iterations | No shared mutation | `Pool.map` / `executor.map` |
| Multiple `requests.get()` or file reads | Sequential I/O | `asyncio.gather()` |
| Nested loops over arrays | Numerical computation | NumPy vectorization |
| `time.sleep()` or blocking waits | Waiting on external | Threading or async |
| Large list comprehensions | Independent transforms | `Pool.map` with chunking |

## Safety Requirements

Always preserve correctness when parallelizing:

1. **Identify shared state** - variables modified across iterations break parallelism
2. **Check dependencies** - iteration N depending on N-1 requires sequential execution
3. **Handle exceptions** - wrap parallel code in try/except, use `executor.submit()` for granular error handling
4. **Manage resources** - use context managers, limit worker count to avoid exhaustion
5. **Preserve ordering** - use `map()` over `submit()` when order matters

## Common Pitfalls

- **GIL trap**: Threading doesn't help CPU-bound Python code—use multiprocessing
- **Pickle failures**: Lambda functions and nested classes can't be pickled for multiprocessing
- **Memory explosion**: ProcessPoolExecutor copies data to each process—use shared memory for large data
- **Async in sync**: Can't just add `async` to existing code—requires restructuring call chain
- **Over-parallelization**: Parallel overhead exceeds gains for small workloads (<1000 items typically)


---

## Advanced Parallelization Techniques

### Shared Memory for Large Data

When passing large arrays between processes, avoid serialization overhead:

```python
import numpy as np
from multiprocessing import shared_memory, Pool

def create_shared_array(data):
    """Create a shared memory array from numpy data."""
    shm = shared_memory.SharedMemory(create=True, size=data.nbytes)
    shared_arr = np.ndarray(data.shape, dtype=data.dtype, buffer=shm.buf)
    shared_arr[:] = data[:]
    return shm, shared_arr

def worker_with_shared(args):
    """Worker that accesses shared memory."""
    shm_name, shape, dtype, chunk_start, chunk_end = args
    existing_shm = shared_memory.SharedMemory(name=shm_name)
    arr = np.ndarray(shape, dtype=dtype, buffer=existing_shm.buf)
    result = process_chunk(arr[chunk_start:chunk_end])
    existing_shm.close()
    return result
```

### Chunked Processing for Memory Efficiency

Process large datasets in chunks to control memory:

```python
from concurrent.futures import ProcessPoolExecutor
from itertools import islice

def chunked(iterable, size):
    """Yield successive chunks from iterable."""
    it = iter(iterable)
    while chunk := list(islice(it, size)):
        yield chunk

def process_large_dataset(items, chunk_size=1000, max_workers=4):
    results = []
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        for chunk in chunked(items, chunk_size):
            chunk_results = list(executor.map(process_item, chunk))
            results.extend(chunk_results)
    return results
```

### Progress Tracking with tqdm

```python
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

def parallel_with_progress(items, process_fn, max_workers=4):
    results = []
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_fn, item): item for item in items}
        for future in tqdm(as_completed(futures), total=len(futures)):
            results.append(future.result())
    return results
```

### Async Semaphore for Rate Limiting

```python
import asyncio
import aiohttp

async def rate_limited_fetch(urls, max_concurrent=10):
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_with_limit(session, url):
        async with semaphore:
            async with session.get(url) as response:
                return await response.json()

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_with_limit(session, url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=True)
```

### Async Queue Pattern for Producer-Consumer

```python
import asyncio

async def producer_consumer(items, num_workers=4):
    queue = asyncio.Queue()
    results = []

    async def producer():
        for item in items:
            await queue.put(item)
        for _ in range(num_workers):
            await queue.put(None)  # Poison pills

    async def consumer():
        while True:
            item = await queue.get()
            if item is None:
                break
            result = await process_async(item)
            results.append(result)
            queue.task_done()

    await asyncio.gather(
        producer(),
        *[consumer() for _ in range(num_workers)]
    )
    return results
```

### ThreadPoolExecutor for Blocking Libraries

Use when async alternatives don't exist:

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

async def async_wrapper_for_blocking(items):
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=10) as executor:
        tasks = [
            loop.run_in_executor(executor, blocking_library_call, item)
            for item in items
        ]
        return await asyncio.gather(*tasks)
```

### Numba JIT for CPU-Intensive Loops

When Python loops can't be easily vectorized:

```python
from numba import jit, prange
import numpy as np

@jit(nopython=True, parallel=True)
def parallel_computation(arr):
    result = np.zeros_like(arr)
    for i in prange(len(arr)):
        result[i] = expensive_math(arr[i])
    return result
```

### Dask for Out-of-Core Computation

For datasets larger than memory:

```python
import dask.dataframe as dd
import dask.array as da

# DataFrame operations
ddf = dd.read_csv('large_file_*.csv')
result = ddf.groupby('category').agg({'value': 'sum'}).compute()

# Array operations
arr = da.from_delayed([delayed_load(f) for f in files], shape=..., dtype=...)
result = arr.mean(axis=0).compute()
```

### Error Handling Patterns

### Graceful degradation with ProcessPoolExecutor:

```python
from concurrent.futures import ProcessPoolExecutor, as_completed

def robust_parallel_process(items, process_fn):
    results = []
    errors = []

    with ProcessPoolExecutor() as executor:
        future_to_item = {executor.submit(process_fn, item): item for item in items}

        for future in as_completed(future_to_item):
            item = future_to_item[future]
            try:
                results.append(future.result())
            except Exception as e:
                errors.append((item, str(e)))

    return results, errors
```

### Async error handling with return_exceptions:

```python
async def safe_gather(tasks):
    results = await asyncio.gather(*tasks, return_exceptions=True)
    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]
    return successes, failures
```
