# Optimize without parallelizing

Task statement:

{task}

Requirements: {requirements}

Plan (route reason: see `plan.route_reason`):

{plan}

Runtime probe: {analysis}

Parallel execution was ruled out for this workload. The goal is memory, or the iterations are dependent, or the workload is too small to amortize a pool. Optimize in place of parallelizing:

1. **Profile first** to find the largest allocations and the hot loops. Use `tracemalloc` (`snapshot.statistics('lineno')`) for allocations, `pympler.asizeof` for deep object sizes when it is installed (`sys.getsizeof` is shallow), `memory_profiler` `@profile` when it is installed, and `cProfile` for time.
2. **Fix algorithmic hotspots** in `plan.algorithmic_fixes_first`.
3. **Pick the memory transformation from what is consuming memory** (`plan.memory_tactics`). Many small objects: `__slots__` or `dataclass(slots=True)`. Lists built all at once: generators. Repeated strings: `sys.intern` or category dtype. Numeric lists: NumPy arrays, only when importable. Whole files: chunked reads or `mmap`. Leaks: bounded caches, `weakref`, explicit cleanup. Load `references/memory-patterns.md` for the code patterns, the per-item memory table, and the leak table.
4. **Keep the API and outputs identical** (`plan.exactness`). Generators change iteration cost, so confirm performance is still acceptable.
5. **Verify by measurement.** Copy the harness below into a scratch directory, set `WORKER_COUNTS = [1]`, and point each `FUNCTIONS` entry's second callable at the optimized code. Measure peak memory for the baseline and the new code in **separate processes**, because `ru_maxrss` is cumulative. Walk `plan.verification_checklist`.

```python
{assets[harness_template]}
```

Answer with the same JSON shape as the parallel route: `deliverable_path` plus a `verification` object (`outputs_match`, `comparison_detail`, `api_ok`, `timings`, `speedups`, `peak_memory_mb`, `baseline_peak_memory_mb`, `errors`, `checklist`). Use `null` for metrics that do not apply.
