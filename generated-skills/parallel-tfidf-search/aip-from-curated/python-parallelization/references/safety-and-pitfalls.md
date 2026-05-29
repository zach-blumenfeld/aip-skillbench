# Safety Requirements & Common Pitfalls

## Safety Requirements

Always preserve correctness when parallelizing.

1. **Identify shared state** — variables modified across iterations break parallelism. Rewrite to return per-iteration values and merge after.
2. **Check dependencies** — if iteration N reads what N-1 wrote, the work is not embarrassingly parallel; either restructure or run sequentially.
3. **Handle exceptions** — wrap parallel code in try/except; use `executor.submit()` + `future.result()` when you need granular per-task error handling.
4. **Manage resources** — use context managers (`with Pool(...) as pool:`); bound worker count to avoid exhausting CPU/memory.
5. **Preserve ordering** — `Pool.map` / `executor.map` preserve input order; `as_completed` does not. Pick deliberately.

## Common Pitfalls

- **GIL trap** — `threading` does NOT speed up CPU-bound pure-Python code. Use `multiprocessing` / `ProcessPoolExecutor` instead.
- **Pickle failures** — `multiprocessing` pickles arguments and worker fns. Lambdas, locally-defined functions, and nested classes can't be pickled. Move worker fns to module top level; pass primitive data.
- **Memory explosion** — `ProcessPoolExecutor` copies arguments to each worker. Large per-call payloads (full corpora, full indexes) destroy speedup. Use the pool **initializer** pattern to load the big object once per worker; pass only small per-call inputs.
- **Async in sync** — you can't sprinkle `async` on existing code; the entire call chain must be async-aware (or bridged via `asyncio.to_thread`/`run_in_executor`).
- **Over-parallelization** — parallel overhead (fork, pickle, IPC) can exceed gains for small workloads (typically < 1000 items, or < 1 ms per item). Fall back to sequential on small inputs.
- **Wrong chunk size** — too few chunks underutilizes workers; too many add IPC overhead. Target ~4× as many chunks as workers, or pass `chunksize=max(1, len(items) // (num_workers * 4))`.
- **Float drift** — parallel reduction order can change the order of float adds, producing tiny differences. Use a tolerance (`abs(a - b) < 1e-6`) when comparing to a sequential baseline.
- **Sorting/tie-breaking** — when two results have identical scores, parallel and sequential may return them in different orders. If the verifier compares ordered lists, sort deterministically (e.g., `(-score, doc_id)`) before returning.

## Worker Count Selection

- Default to `multiprocessing.cpu_count()` when the task doesn't specify.
- When the task hard-codes a number (e.g., "with 4 workers"), honor it in the test fixture but let `num_workers=None` mean cpu_count in the production interface.
- On NUMA / containerized hosts, `os.sched_getaffinity(0)` is more accurate than `cpu_count()`. Use the simpler call unless the task requires otherwise.

## Verification Checklist

Before declaring parallel code done:

- [ ] Output matches sequential version on representative inputs (within float tolerance for reductions).
- [ ] No race conditions — verify no shared mutable state across workers.
- [ ] Exceptions surface from workers (don't silently drop them).
- [ ] All pools, executors, and connections close cleanly (use `with` blocks).
- [ ] Worker count is bounded (default or explicit limit).
- [ ] Worker functions are at module top level (pickle-safe).
- [ ] Speedup meets the task's stated target on the task's hardware (e.g., ≥ 1.5× index build, ≥ 2× batch search with 4 workers).
