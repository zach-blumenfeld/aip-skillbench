# Load-balancing strategies

Code for the strategy named in `plan.balancing` / `plan.best_balance`. Comes from the workload-balancing skill and its distributed-pattern reference. Fixed in this copy: Strategy 2 now imports `wait`/`FIRST_COMPLETED` and pops pending items from a deque. `rebalance_on_straggler` is pseudo-code: `completion_times`, `elapsed`, `cancel_and_get_remaining` and `redistribute` are yours to supply.

## Balancing Strategies

### Strategy 1: Static Chunking (Uniform Workloads)

Best for: predictable, similar-sized tasks

```python
from concurrent.futures import ProcessPoolExecutor
import numpy as np

def static_balanced_process(items, num_workers=4):
    """Divide work into equal chunks upfront."""
    chunks = np.array_split(items, num_workers)

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        results = list(executor.map(process_chunk, chunks))

    return [item for chunk_result in results for item in chunk_result]
```

### Strategy 2: Dynamic Task Queue (Variable Workloads)

Best for: unpredictable task durations

```python
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait

def dynamic_balanced_process(items, num_workers=4):
    """Workers pull tasks dynamically as they complete."""
    results = []

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        # Submit one task per worker initially
        futures = {executor.submit(process_item, item): item
                   for item in items[:num_workers]}
        pending = deque(items[num_workers:])

        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)

            for future in done:
                results.append(future.result())
                del futures[future]

                # Submit next task if available
                if pending:
                    next_item = pending.popleft()
                    futures[executor.submit(process_item, next_item)] = next_item

    return results
```

### Strategy 3: Work Stealing (Long-Tail Tasks)

Best for: when some tasks take much longer than others

```python
import asyncio
from collections import deque

class WorkStealingPool:
    def __init__(self, num_workers):
        self.queues = [deque() for _ in range(num_workers)]
        self.num_workers = num_workers

    def distribute(self, items):
        """Initial round-robin distribution."""
        for i, item in enumerate(items):
            self.queues[i % self.num_workers].append(item)

    async def worker(self, worker_id, process_fn):
        """Process own queue, steal from others when empty."""
        while True:
            # Try own queue first
            if self.queues[worker_id]:
                item = self.queues[worker_id].popleft()
            else:
                # Steal from busiest queue
                item = self._steal_work(worker_id)
                if item is None:
                    break

            await process_fn(item)

    def _steal_work(self, worker_id):
        """Steal from the queue with most items."""
        busiest = max(range(self.num_workers),
                      key=lambda i: len(self.queues[i]) if i != worker_id else 0)
        if self.queues[busiest]:
            return self.queues[busiest].pop()  # Steal from end
        return None
```

### Strategy 4: Weighted Distribution

Best for: when task costs are known or estimable

```python
def weighted_partition(items, weights, num_workers):
    """Partition items to balance total weight per worker."""
    # Sort by weight descending (largest first fit)
    sorted_items = sorted(zip(items, weights), key=lambda x: -x[1])

    worker_loads = [0] * num_workers
    worker_items = [[] for _ in range(num_workers)]

    for item, weight in sorted_items:
        # Assign to least loaded worker
        min_worker = min(range(num_workers), key=lambda i: worker_loads[i])
        worker_items[min_worker].append(item)
        worker_loads[min_worker] += weight

    return worker_items
```

### Strategy 5: Async Semaphore Balancing (I/O Workloads)

Best for: limiting concurrent I/O operations

```python
import asyncio

async def semaphore_balanced_fetch(urls, max_concurrent=10):
    """Limit concurrent operations while processing queue."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def bounded_fetch(url):
        async with semaphore:
            return await fetch(url)

    return await asyncio.gather(*[bounded_fetch(url) for url in urls])
```

## Partitioning Strategies

| Strategy | Best For | Implementation |
|----------|----------|----------------|
| Equal chunks | Uniform tasks | `np.array_split(items, n)` |
| Round-robin | Streaming | `items[i::n_workers]` |
| Size-weighted | Known sizes | Bin packing algorithm |
| Hash-based | Consistent routing | `hash(key) % n_workers` |
| Range-based | Sorted/ordered data | Contiguous ranges |

## Handling Stragglers

Techniques to mitigate slow workers:

```python
# 1. Timeout with fallback
from concurrent.futures import TimeoutError

try:
    result = future.result(timeout=30)
except TimeoutError:
    result = fallback_value

# 2. Speculative execution (backup tasks)
async def speculative_execute(task, timeout=10):
    primary = asyncio.create_task(execute(task))
    try:
        return await asyncio.wait_for(primary, timeout)
    except asyncio.TimeoutError:
        backup = asyncio.create_task(execute(task))  # Retry
        done, pending = await asyncio.wait(
            [primary, backup], return_when=asyncio.FIRST_COMPLETED
        )
        for p in pending:
            p.cancel()
        return done.pop().result()

# 3. Dynamic rebalancing
def rebalance_on_straggler(futures, threshold_ratio=2.0):
    """Redistribute work if one worker falls behind."""
    avg_completion = statistics.mean(completion_times)
    for future, worker_id in futures.items():
        if future.running() and elapsed(future) > threshold_ratio * avg_completion:
            # Cancel and redistribute
            remaining_work = cancel_and_get_remaining(future)
            redistribute(remaining_work, fast_workers)
```

## Monitoring Metrics

Track these for balanced execution:

| Metric | Calculation | Target |
|--------|-------------|--------|
| Load imbalance | `max(load) / avg(load)` | < 1.2 |
| Straggler ratio | `max(time) / median(time)` | < 2.0 |
| Worker utilization | `busy_time / total_time` | > 90% |
| Queue depth variance | `std(queue_lengths)` | Low |

## Anti-Patterns

| Problem | Cause | Fix |
|---------|-------|-----|
| Starvation | Large tasks block queue | Break into subtasks |
| Thundering herd | All workers wake at once | Jittered scheduling |
| Hot spots | Uneven key distribution | Better hash function |
| Convoy effect | Workers wait on same resource | Fine-grained locking |
| Over-partitioning | Too many small tasks | Batch small items |


---

## Distributed Workload Patterns

### Consistent Hashing for Distributed Systems

Route requests to workers while minimizing redistribution on scaling:

```python
import hashlib
from bisect import bisect_right

class ConsistentHash:
    def __init__(self, nodes, virtual_nodes=100):
        self.ring = []
        self.node_map = {}

        for node in nodes:
            for i in range(virtual_nodes):
                key = self._hash(f"{node}:{i}")
                self.ring.append(key)
                self.node_map[key] = node

        self.ring.sort()

    def _hash(self, key):
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def get_node(self, key):
        """Get the node responsible for this key."""
        if not self.ring:
            return None

        hash_key = self._hash(str(key))
        idx = bisect_right(self.ring, hash_key) % len(self.ring)
        return self.node_map[self.ring[idx]]
```

### Rate-Limited Queue with Backpressure

Prevent overwhelming downstream services:

```python
import asyncio
from datetime import datetime, timedelta

class RateLimitedQueue:
    def __init__(self, max_rate, time_window=1.0):
        self.max_rate = max_rate
        self.time_window = time_window
        self.timestamps = []
        self.queue = asyncio.Queue()
        self._lock = asyncio.Lock()

    async def put(self, item):
        await self.queue.put(item)

    async def get(self):
        async with self._lock:
            await self._wait_for_capacity()
            self.timestamps.append(datetime.now())
            return await self.queue.get()

    async def _wait_for_capacity(self):
        while True:
            cutoff = datetime.now() - timedelta(seconds=self.time_window)
            self.timestamps = [t for t in self.timestamps if t > cutoff]

            if len(self.timestamps) < self.max_rate:
                return

            # Wait until oldest timestamp expires
            wait_time = (self.timestamps[0] + timedelta(seconds=self.time_window)
                        - datetime.now()).total_seconds()
            await asyncio.sleep(max(0, wait_time))
```

### Priority-Based Load Balancing

Handle different priority levels:

```python
import heapq
from dataclasses import dataclass, field
from typing import Any

@dataclass(order=True)
class PriorityTask:
    priority: int
    item: Any = field(compare=False)

class PriorityBalancer:
    def __init__(self, num_workers):
        self.queues = [[] for _ in range(num_workers)]
        self.worker_loads = [0] * num_workers

    def submit(self, item, priority=0, estimated_cost=1):
        """Submit task to least loaded worker."""
        worker = min(range(len(self.queues)),
                    key=lambda i: self.worker_loads[i])

        heapq.heappush(self.queues[worker], PriorityTask(priority, item))
        self.worker_loads[worker] += estimated_cost

    def get_next(self, worker_id):
        """Get highest priority task for worker."""
        if self.queues[worker_id]:
            task = heapq.heappop(self.queues[worker_id])
            return task.item
        return None
```

### Circuit Breaker Pattern

Prevent cascading failures:

```python
import time
from enum import Enum
from functools import wraps

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery

class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=30):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED

    def __call__(self, func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                else:
                    raise Exception("Circuit breaker is open")

            try:
                result = await func(*args, **kwargs)
                self._on_success()
                return result
            except Exception as e:
                self._on_failure()
                raise

        return wrapper

    def _on_success(self):
        self.failures = 0
        self.state = CircuitState.CLOSED

    def _on_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
```

### Adaptive Batch Sizing

Dynamically adjust batch size based on performance:

```python
class AdaptiveBatcher:
    def __init__(self, initial_size=100, min_size=10, max_size=10000):
        self.batch_size = initial_size
        self.min_size = min_size
        self.max_size = max_size
        self.last_throughput = 0

    def adjust(self, items_processed, elapsed_time):
        """Adjust batch size based on throughput."""
        throughput = items_processed / elapsed_time if elapsed_time > 0 else 0

        if throughput > self.last_throughput * 1.1:
            # Throughput improving, increase batch size
            self.batch_size = min(self.batch_size * 2, self.max_size)
        elif throughput < self.last_throughput * 0.9:
            # Throughput degrading, decrease batch size
            self.batch_size = max(self.batch_size // 2, self.min_size)

        self.last_throughput = throughput
        return self.batch_size
```

### Locality-Aware Scheduling

Prefer workers with cached data:

```python
class LocalityAwareScheduler:
    def __init__(self, workers):
        self.workers = workers
        self.worker_cache = {w: set() for w in workers}

    def schedule(self, task):
        """Schedule task to worker with best data locality."""
        task_keys = set(task.required_keys)

        # Score workers by cache hits
        scores = []
        for worker in self.workers:
            cache_hits = len(task_keys & self.worker_cache[worker])
            load = self.get_worker_load(worker)
            # Balance locality vs load
            score = cache_hits * 10 - load
            scores.append((score, worker))

        best_worker = max(scores, key=lambda x: x[0])[1]
        self.worker_cache[best_worker].update(task_keys)
        return best_worker
```

### MapReduce-Style Shuffling

Efficient data redistribution:

```python
from collections import defaultdict

def map_phase(items, map_fn, num_reducers):
    """Map items and partition by key for reducers."""
    partitions = defaultdict(list)

    for item in items:
        for key, value in map_fn(item):
            partition_id = hash(key) % num_reducers
            partitions[partition_id].append((key, value))

    return partitions

def shuffle_and_reduce(partitions, reduce_fn):
    """Shuffle data to reducers and apply reduce function."""
    results = {}

    for partition_id, pairs in partitions.items():
        # Group by key
        grouped = defaultdict(list)
        for key, value in pairs:
            grouped[key].append(value)

        # Reduce each group
        for key, values in grouped.items():
            results[key] = reduce_fn(key, values)

    return results
```

### Exponential Backoff with Jitter

Prevent thundering herd on retries:

```python
import random
import asyncio

async def retry_with_backoff(func, max_retries=5, base_delay=1.0):
    """Retry with exponential backoff and jitter."""
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise

            # Exponential backoff with full jitter
            delay = base_delay * (2 ** attempt)
            jittered_delay = random.uniform(0, delay)
            await asyncio.sleep(jittered_delay)
```
