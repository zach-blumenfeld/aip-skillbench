---
name: parallelize-python
description: Speed up sequential Python code by parallelizing it and balancing its workload, with memory kept in check and results identical to the original. Use when asked to parallelize Python code, convert loops to multiprocessing, threading, asyncio or vectorized form, speed up a CPU-bound pipeline such as TF-IDF indexing, inverted-index building or batch search, balance uneven work across workers, fix stragglers, or reduce memory footprint or leaks. Profiles the baseline, classifies the workload (CPU/I-O/data-parallel; uniform/variable/long-tail), plans the executor, partitioning and shared-data strategy, then implements and verifies speedup and output equality.
metadata:
  aip-version: "0.5a1"
---

# AIP runtime — format 0.5a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the JSON object a step receives. Each step declares its required keys as `inputs`; extra keys pass through.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the final state's shape.

## Execution

The state is one JSON object. It starts as the start step's `inputs` and flows along `inputs_to`; each step's output is merged over it, so keys accumulate and extra keys pass through untouched. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. You may change the state before any step runs; you have the final say at every step.

- **`execution`**: run `script` with one JSON object on stdin, `{"currentState": <state>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout; merge it over the state.
- **`decision`**: answer each question against the state. Each answer collapses to one value under its question name and is merged over the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the state, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the next step's `inputs`; merge them over the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. That state is the procedure's result.


```yaml
purpose: >
  Turn sequential Python into a faster parallel (or, when parallelism cannot pay, a leaner
  sequential) implementation whose outputs match the original exactly. One workflow merges
  three skills: python-parallelization (CPU/I-O/data-parallel strategy), workload-balancing
  (partitioning, stragglers, metrics) and memory-optimization (worker copies, data structures,
  leaks). Scripts scan the code for quadratic hotspots and picklability traps, probe the
  container (usable CPUs incl. cgroup quota, start methods, importable packages), simulate
  partitioning on measured item costs, apply Amdahl and over-parallelization checks, and
  grade the measured result.

trigger_when:
  - Asked to parallelize Python code, convert loops to parallel execution, or identify parallelization opportunities.
  - Asked to speed up a sequential implementation with multiprocessing, threading, asyncio, concurrent.futures or vectorization, e.g. a parallel TF-IDF index build, inverted index or batch query search.
  - Asked to balance work across workers, reduce stragglers, implement load balancing or optimize task scheduling.
  - Asked to reduce memory footprint, fix memory leaks, handle large datasets efficiently, or keep parallel workers within a memory limit.
  - A task supplies a sequential baseline and requires a faster version with identical results at given worker counts.

do_not_use_when:
  - The code is not Python, or the bottleneck lives in an external service the code cannot change.
  - The request is distributed-cluster orchestration (Spark/Kubernetes job design) rather than in-process Python code.
  - Pure algorithm design with no performance or memory goal.

steps:
  - name: inspect
    kind: execution
    description: Statically scan the sequential code for hotspots and parallelization traps, probe CPUs/start methods/memory/packages, and optionally cProfile the baseline.
    inputs:
      - name: task
        type: string
        description: The task statement, verbatim (deliverable, API, worker counts, thresholds).
      - name: target_path
        type: string
        description: Absolute path of the sequential code (file or directory), e.g. /root/workspace.
      - name: profile_command
        type: string
        description: Baseline entry point to profile, run with the target directory as cwd (e.g. "python sequential.py --num-docs 3000"; pass explicit paths for any data it writes or reads), or "" to skip. Optional extra start key python_executable names the task's interpreter to probe and profile with.
    script: scripts/inspect_target.py
    timeout: 900
    inputs_to: characterize

  - name: characterize
    kind: client_task
    description: Extract the exact requirements from the task and measure the baseline (per-phase time, parallel fraction, per-item cost proxy, peak memory).
    inputs:
      - name: task
        type: string
      - name: target_path
        type: string
      - name: analysis
        type: object
        description: Output of inspect (environment, static scan, profile).
    template: assets/characterize.md
    inputs_to: classify

  - name: classify
    kind: decision
    description: Classify the goal, workload type, dependency structure, cost variance, shared-input size and exactness requirement.
    inputs:
      - name: task
        type: string
      - name: analysis
        type: object
      - name: requirements
        type: object
      - name: workload
        type: object
    questions:
      goal:
        type: choice
        instructions: What must the change achieve, per the task statement? Judge from what the task measures or demands, not from what would be nice.
        criteria:
          speed: Faster execution (speedup, throughput, parallel implementation) is required; memory is not a stated target.
          memory: Lower memory use, leak fixes or large-data handling is the target; speed is secondary.
          both: The task states both a speed and a memory target.
      workload_type:
        type: choice
        instructions: Where is the measured bottleneck of the code to optimize (use workload.phase_seconds and analysis.static.io_calls, not the program's input generation)?
        criteria:
          cpu_bound: Pure-Python computation dominates (parsing, tokenizing, dict/loop math).
          io_bound: Waiting on network, disk, database or sleep dominates.
          data_parallel: Numeric array/matrix or DataFrame operations dominate and can be expressed as vectorized ops.
          mixed: Substantial CPU work and substantial I/O waiting both matter.
      dependency:
        type: choice
        instructions: How do the iterations of the expensive work relate to each other?
        criteria:
          independent: Each item's result depends only on that item (map).
          mergeable_reduction: Items are independent but feed a global aggregate (counts, vocabulary, index) that can be merged from per-chunk partials.
          true_shared_state: Iterations read and write a shared mutable structure that cannot be split into partials.
          loop_carried: Iteration N needs the result of iteration N-1.
      task_variance:
        type: choice
        instructions: How variable is the cost per work item? Use workload.item_weights (cost proxy) when present.
        criteria:
          uniform: Items cost about the same (workload.weight_stats.cv < 0.25).
          variable_predictable: Costs vary (cv >= 0.25) and a cheap proxy (length, size, row count) predicts them, with max_over_median <= 20 and max_share <= 0.05.
          variable_unpredictable: Costs vary and nothing cheap predicts them (no usable proxy was measured).
          long_tail: A proxy exists but the largest items dominate - max_over_median > 20 or one item > 5% of the total (max_share > 0.05); this wins over variable_predictable.
      large_shared_input:
        type: noul
        instructions: Do all workers need read access to a large structure (an index, model, corpus or array of tens of MB or more) that would be costly to pickle per task?
      exact_match_required:
        type: noul
        instructions: Must outputs equal the sequential baseline's exactly (same values, ordering and types), as opposed to within a stated tolerance or loosely?
        criteria:
          true: The task says identical/same results, compares against the baseline, or gives no tolerance.
          false: The task explicitly allows approximate results, a tolerance, or a different order.
    thresholds:
      goal: 0.7
      workload_type: 0.6
      dependency: 0.6
      task_variance: 0.5
      large_shared_input: 0.2
      exact_match_required: 0.3
    inputs_to: plan

  - name: plan
    kind: execution
    description: Map the classification through the encoded decision trees to an executor, partitioning (simulated on item weights), shared-data and memory plan, and route parallelize vs optimize_sequential.
    inputs:
      - name: analysis
        type: object
      - name: requirements
        type: object
      - name: workload
        type: object
      - name: goal
        type: string
      - name: workload_type
        type: string
      - name: dependency
        type: string
      - name: task_variance
        type: string
      - name: large_shared_input
        type: boolean
      - name: exact_match_required
        type: boolean
    script: scripts/plan_strategy.py
    assets:
      - assets/strategy_rules.json
    inputs_to: by-route

  - name: by-route
    kind: router
    description: Parallelize when independent or mergeable work is large enough (or required); otherwise optimize the sequential code.
    branch_on: route
    branches:
      parallelize: implement-parallel
      optimize_sequential: implement-sequential

  - name: implement-parallel
    kind: client_task
    description: Write the parallel deliverable per the plan (algorithmic fixes, executor, balanced chunks, shared input, linear merge, fast path) and verify it with the harness.
    inputs:
      - name: task
        type: string
      - name: requirements
        type: object
      - name: plan
        type: object
      - name: analysis
        type: object
    template: assets/implement_parallel.md
    assets:
      - assets/harness_template.py
    references:
      - path: references/parallel-patterns.md
        description: Executor code patterns (ProcessPoolExecutor, asyncio, vectorization, hybrid), shared memory, chunking, producer-consumer, numba, dask, error handling. Load when writing the executor code.
      - path: references/balancing-strategies.md
        description: Static/dynamic/work-stealing/weighted/semaphore code, partitioning table, straggler handling, monitoring metrics and balancing anti-patterns. Load when items vary in cost or imbalance is over target.
      - path: references/memory-patterns.md
        description: Memory decision tree, __slots__/generators/downcast/interning/mmap/chunking, size and leak tables, profiling commands. Load when worker copies threaten the memory limit.
      - path: references/map-reduce-index.md
        description: Measured pattern and exactness gotchas for parallel TF-IDF / inverted index / counting builds and batch query search. Load when the target aggregates per-item data into a global index or scores queries against one.
    inputs_to: evaluate

  - name: implement-sequential
    kind: client_task
    description: Optimize memory and algorithmic hotspots without parallelism, keeping the API and outputs identical, and verify with the harness.
    inputs:
      - name: task
        type: string
      - name: requirements
        type: object
      - name: plan
        type: object
      - name: analysis
        type: object
    template: assets/implement_sequential.md
    assets:
      - assets/harness_template.py
    references:
      - path: references/memory-patterns.md
        description: Memory transformation patterns, data-structure size table, leak table, profiling commands and advanced patterns (object pool, weakref cache, COW, SoA, flyweight, sparse, pandas, streaming JSON).
      - path: references/map-reduce-index.md
        description: One-pass replacements for quadratic aggregate loops (document frequency, postings) and exactness gotchas. Load when the target builds an index or counts.
    inputs_to: evaluate

  - name: evaluate
    kind: execution
    description: Grade the measured verification (output equality, errors, API, speedup per worker count, imbalance, stragglers, utilization, memory) and decide pass / revise / stop.
    inputs:
      - name: deliverable_path
        type: string
      - name: verification
        type: object
        description: Measured results from the harness.
      - name: requirements
        type: object
      - name: plan
        type: object
      - name: goal
        type: string
    script: scripts/evaluate.py
    inputs_to: by-verdict

  - name: by-verdict
    kind: router
    description: Finish on pass; fix and re-measure on revise; stop after the attempt limit and report remaining failures.
    branch_on: verdict_status
    branches:
      pass: end
      revise: revise
      stop: end

  - name: revise
    kind: client_task
    description: Fix every failure in the verdict and re-run the same verification.
    inputs:
      - name: deliverable_path
        type: string
      - name: verdict
        type: object
      - name: verification
        type: object
      - name: plan
        type: object
      - name: requirements
        type: object
    template: assets/revise.md
    references:
      - path: references/parallel-patterns.md
        description: Executor patterns and error handling.
      - path: references/balancing-strategies.md
        description: Rebalancing and straggler fixes.
      - path: references/memory-patterns.md
        description: Memory reductions when the limit is exceeded.
      - path: references/map-reduce-index.md
        description: Exactness gotchas (tie order, float order, field types) for index/aggregate builds and batch search.
    inputs_to: evaluate

  - name: end
    kind: end
    description: The written deliverable with its measured verification and the final verdict (passed, or stopped with the listed failures).
    inputs:
      - name: deliverable_path
        type: string
      - name: verification
        type: object
      - name: verdict
        type: object

anti_patterns:
  - Parallelizing an O(n*m) loop instead of first rewriting it as one linear pass; the quadratic loop stays the bottleneck.
  - Using threads for CPU-bound pure-Python work (GIL) or processes for tiny workloads (pool start-up and pickling exceed the gain).
  - Passing lambdas, nested functions or nested classes to a process pool (pickle failure).
  - Shipping a large read-only index/model with every task instead of inheriting it via fork or an initializer; relying on fork without asking for it on Python 3.14+/macOS.
  - Collecting results in completion order (as_completed) when the output order must match the input.
  - Changing float accumulation order or list insertion order and then calling the results "equal enough" when the task demands identical output.
  - Timing the whole program (including input generation) instead of the function being optimized; claiming speedup without measuring it at the task's worker counts.
  - Starvation (one large task blocks the queue - break it into subtasks), thundering herd (all workers wake at once - jitter), hot spots (uneven key distribution - better hash), convoy effect (workers wait on one resource - finer-grained locking), over-partitioning (too many tiny tasks - batch them).
  - Requesting more workers than usable CPUs (cgroup quota/affinity) and expecting linear speedup.
  - Leaving scratch benchmark or harness files inside the deliverable folder.
```
