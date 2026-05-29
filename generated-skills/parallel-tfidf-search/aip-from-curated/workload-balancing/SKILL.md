---
name: workload-balancing
description: Optimize workload distribution across workers, processes, or nodes for efficient parallel execution. Use when asked to balance work distribution, improve parallel efficiency, reduce stragglers, implement load balancing, or optimize task scheduling. Covers static/dynamic partitioning, work stealing, weighted distribution, async semaphore balancing, and adaptive strategies, plus straggler mitigation and balance-metric verification.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Distribute work across parallel workers (processes, threads, async tasks, or
  distributed nodes) so throughput is maximized and the slowest worker does not
  dominate wall-clock time. Selects a balancing strategy from workload
  characteristics, supplies reference implementations for the five canonical
  patterns, scripts the deterministic pieces (LPT weighted partitioning,
  imbalance metrics), and gates completion on measured balance — not just
  "code ran".

trigger_when:
  - User asks to balance work distribution across workers, processes, or nodes.
  - User asks to improve parallel efficiency or reduce stragglers.
  - User asks to implement load balancing or task scheduling.
  - Parallel code completes but one worker dominates wall-clock time.
  - Choosing between static partitioning, dynamic queues, or work stealing.
  - Optimizing a parallel batch workload (e.g., parallel TF-IDF indexing or batch search).
  - Distributing variable-cost tasks where naive equal chunking would create skew.

do_not_use_when:
  - Work is genuinely sequential — no parallelism opportunity exists.
  - The bottleneck is single-thread CPU, memory, or I/O latency rather than uneven distribution.
  - Picking the parallelism *primitive* itself (processes vs threads vs async) — use a python-parallelization skill for that decision and return here once the executor is chosen.
  - Optimizing per-worker memory footprint — use a memory-optimization skill; return here for cross-worker distribution.

scope_and_approval: >
  Read-only by default. Code edits, dependency additions, and benchmark runs
  require the same authorization the host project requires for source changes.
  The `measure-balance` step is safe to run unattended on captured timing data.

steps:
  - name: characterize-workload
    description: >
      Profile the workload before choosing a strategy. Determine (a) task-time
      distribution — uniform, predictably variable, or long-tail; (b) input
      arrival pattern — known count vs streaming; (c) per-item cost estimability
      — known weights, estimable weights, or unknown; (d) resource constraints —
      memory-bound, heterogeneous workers, network/data-locality cost. Sample a
      handful of items with the real processing function if no profile exists.
    outputs:
      - name: workload-profile
        type: object
        description: "{task_time_variance, input_pattern, cost_estimability, resource_constraints}"

  - name: identify-bottlenecks
    description: >
      Inspect existing runs (or a quick benchmark) for straggler workers, idle
      workers waiting on a queue, hot keys, or memory pressure. If no run
      exists, predict the likely bottleneck from the profile (e.g., variable
      task times + static chunking → stragglers).
    inputs:
      - name: workload-profile
        type: object
    outputs:
      - name: bottleneck-report
        type: object
        description: "{straggler_observed, idle_workers, hot_keys, memory_pressure}"

  - name: select-strategy
    description: >
      Apply the decision tree, then pick exactly one strategy as the primary;
      auxiliary patterns (semaphores, work stealing) may layer in implement.

      Decision tree:
        Uniform task times:
          known count          → Static Chunking (equal chunks)
          streaming input      → Round-Robin distribution
          large items          → Size-aware (weighted) partitioning
        Variable task times:
          predictable variance → Weighted Distribution (LPT)
          unpredictable        → Dynamic Task Queue / work stealing
          long-tail            → Work Stealing + per-task time limits
        Resource constraints:
          memory-bound workers → memory-aware assignment
          heterogeneous workers → capability-based routing
          network costs        → locality-aware placement
        I/O-bound concurrency  → Async Semaphore Balancing

      Partitioning quick-reference:
        equal chunks    np.array_split(items, n)        uniform tasks
        round-robin     items[i::n_workers]             streaming
        size-weighted   LPT bin packing (script)        known sizes
        hash-based      hash(key) % n_workers           consistent routing
        range-based     contiguous ranges               sorted/ordered data
    inputs:
      - name: workload-profile
        type: object
      - name: bottleneck-report
        type: object
    outputs:
      - name: strategy-choice
        type: object
        description: "{primary, auxiliary[], reasoning}"
    one_of:
      - static-chunking
      - round-robin
      - weighted-distribution
      - dynamic-task-queue
      - work-stealing
      - async-semaphore
      - hash-routing
      - locality-aware

  - name: implement-balancing
    description: >
      Adapt the matching reference pattern into the codebase. The patterns
      below are the canonical implementations; preserve their structure and
      change only what the integration requires.

      Strategy 1 — Static Chunking (uniform tasks, known count):
        chunks = np.array_split(items, num_workers)
        with ProcessPoolExecutor(max_workers=num_workers) as ex:
            results = list(ex.map(process_chunk, chunks))
        return [x for chunk in results for x in chunk]
        When workers need a large shared resource (e.g., a TF-IDF index),
        pass it via `initializer=`/`initargs=` so each worker builds or
        loads it once, instead of pickling per call.

      Strategy 2 — Dynamic Task Queue (variable task times):
        Seed one task per worker, then on each completion submit the next
        pending item. Uses concurrent.futures.wait with FIRST_COMPLETED.

      Strategy 3 — Work Stealing (long-tail):
        Round-robin distribute, each worker pops from the head of its own
        deque, steals from the *tail* of the busiest deque when own queue
        is empty. See original-SKILL.md (Strategy 3) for the WorkStealingPool
        reference; preserve head/tail asymmetry.

      Strategy 4 — Weighted Distribution (known/estimable costs):
        Call `scripts/weighted_partition.py` with items + weights +
        num_workers. Uses LPT (longest-processing-time first) bin packing
        for a 4/3-approximation makespan. Avoid hand-rolling.

      Strategy 5 — Async Semaphore (I/O concurrency cap):
        sem = asyncio.Semaphore(max_concurrent)
        async def bounded(x):
            async with sem:
                return await fetch(x)
        return await asyncio.gather(*[bounded(x) for x in xs])

      For distributed-system patterns (consistent hashing, rate-limited
      queue, priority balancing, circuit breaker, adaptive batching,
      locality-aware scheduling, MapReduce shuffle, exponential backoff
      with jitter), read `references/advanced_techniques.md` before
      writing code.
    inputs:
      - name: strategy-choice
        type: object
    outputs:
      - name: balanced-code
        type: string
        description: path or diff of the implementation

  - name: handle-stragglers
    description: >
      Add straggler mitigation to the implementation. Pick whichever fits the
      strategy:
        1. Timeout-with-fallback — `future.result(timeout=N)` and a
           degraded-but-correct fallback value.
        2. Speculative execution — start a backup task after a soft timeout;
           the first to finish wins; cancel the rest.
        3. Dynamic rebalancing — when a worker's elapsed time exceeds
           `threshold_ratio * mean(completion_times)` (suggested 2.0), cancel
           and redistribute its remaining work to fast workers.
      Pair with the partitioning choice: static chunking benefits most from
      rebalancing; async I/O benefits most from speculative execution; dynamic
      queues need only timeout fallback because re-dispatch is cheap.
    outputs:
      - name: straggler-policy
        type: object
        description: "{technique, threshold_ratio?, fallback_value?}"

  - name: measure-balance
    description: >
      Compute load-imbalance, straggler ratio, worker utilization, and
      queue-depth variance from captured per-worker timings. Pass/fail
      verdicts come back with the source-skill targets baked in
      (imbalance < 1.2, straggler < 2.0, utilization > 0.9).
    script: scripts/balance_metrics.py
    inputs:
      - name: worker-timings
        type: object
        description: "{worker_times[], worker_loads[]?, queue_lengths[]?, wall_clock?}"
    outputs:
      - name: imbalance-metrics
        type: object
        description: "per-metric value + verdict; _summary.balanced is true when all targets pass"

  - name: verify-and-iterate
    description: >
      Walk the checklist and fix what failed:
        1. Distribution is roughly even — `imbalance-metrics._summary.balanced` is true.
        2. No starvation — every worker stayed busy (utilization > 0.9).
        3. Stragglers handled — no worker time > 2.0× median, or straggler policy fires.
        4. Overhead is acceptable — partitioning + coordination cost < per-task cost.
        5. Results are complete and correct — identical to sequential reference (assert).
        6. Speedup target met — wall-clock / sequential meets stated goal (e.g., 1.5× or 2×).
      If any check fails, re-enter `select-strategy` with the new evidence —
      don't tune the wrong strategy.
    inputs:
      - name: imbalance-metrics
        type: object
      - name: straggler-policy
        type: object
    outputs:
      - name: verification-report
        type: object

anti_patterns:
  - "Starvation — one large task blocks the queue. Fix — break into subtasks and cap per-task size."
  - "Thundering herd — all workers wake or retry at once. Fix — jittered scheduling, exponential backoff with full jitter."
  - "Hot spots — uneven key distribution funnels load to one worker. Fix — better hash function or consistent hashing with virtual nodes."
  - "Convoy effect — workers serialize on a shared lock. Fix — fine-grained locking, per-shard state."
  - "Over-partitioning — chunks so small that coordination dominates. Fix — batch small items, raise chunk size until partitioning cost is amortized."
  - "Equal chunking on variable-cost data — np.array_split on heterogeneous items guarantees a straggler. Use weighted distribution or a dynamic queue instead."
  - "Tuning a balancing strategy that doesn't match the workload — re-run select-strategy when verification fails, do not patch the wrong choice."
  - "Declaring success without measuring — 'it ran' is not balanced. Require measure-balance to pass before reporting done."

scenarios:
  - need: Parallelize TF-IDF index build over a corpus of variable-length documents on 4 cores; target 1.5× speedup.
    context: Documents range from 100 to 50k tokens. Sequential build is CPU-bound; per-document cost ≈ length.
    action: characterize → variable cost, estimable from `len(doc)`. select-strategy → weighted-distribution. implement → `weighted_partition.py` with weights = doc lengths, then ProcessPoolExecutor.map per bin. measure-balance with per-worker times.
    outcome: Load imbalance 1.08, straggler ratio 1.3, 1.7× speedup vs sequential.

  - need: Parallel batch search over many queries against a shared TF-IDF index; target 2× speedup at 4 workers.
    context: Each query cost roughly equal (top-k retrieval on a fixed index); query count fixed and known.
    action: characterize → uniform, known count. select-strategy → static-chunking. implement → `np.array_split(queries, 4)` + ProcessPoolExecutor.map. measure-balance.
    outcome: Imbalance 1.04, utilization 0.94, 2.1× speedup.

  - need: Variable-cost crawl of N URLs hitting a rate-limited API; some pages 10× slower than others.
    context: Cannot predict per-URL latency; rate cap 20 req/s.
    action: select-strategy → dynamic-task-queue with auxiliary async-semaphore. implement → semaphore(20) + dynamic task queue with as_completed. handle-stragglers → timeout with fallback. measure-balance.
    outcome: Utilization 0.93, no straggler exceeded 2× median; throughput at rate-cap ceiling.

  - need: Long-tail batch where 1% of items take 100× the median.
    context: A few "heavy" items would freeze a static partition.
    action: select-strategy → work-stealing. implement Strategy 3. handle-stragglers → speculative execution on the heaviest 1%. measure-balance with queue_lengths captured every second.
    outcome: queue_depth_stddev low; max worker time within 1.8× median.
```
