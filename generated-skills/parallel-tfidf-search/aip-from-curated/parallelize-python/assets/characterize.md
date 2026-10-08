# Characterize the task and measure the baseline

Task statement:

{task}

Sequential code under `{target_path}`. Static scan, runtime probe and (optional) profile from the previous step:

{analysis}

Do the following, then answer with the JSON object at the end.

0. **Interpreter.** `analysis.environment.probed_interpreter` is the Python that was probed. If the task runs under a different one (a container's python, a venv), run every measurement below with that interpreter. Re-check its start method, CPU count and packages if `analysis` was not probed with it.
1. **Extract the requirements from the task statement, word for word where it names things.** The deliverable file path, the exact function/class names and signatures (parameter names, defaults, return types), the worker counts it will be run with, any speedup or memory threshold, the correctness criterion (identical results, tolerance, same ordering), and whether a parallel implementation is explicitly required. When the task gives none of these, infer them from the baseline's API: mirror each sequential function as a `*_parallel` counterpart with the same parameters plus `num_workers`. If the task names neither a file nor a directory, write next to the baseline.
2. **Read every file under the target path end to end.** Identify the functions to optimize and the phases inside them (e.g. per-item parse/tokenize, global aggregation, per-item scoring, final sort). Check `analysis.static.hotspots`: an O(n×m) loop over two independent collections is an algorithmic fix to make before or alongside parallelizing.
3. **Time the target function alone, not the program.** The profile in `analysis.profile` covers the whole entry point and can be dominated by input generation or I/O setup; ignore those parts. Write a small timing script in a scratch directory outside the deliverable folder. Import the baseline module, build the input once at the size the task states (or the code's own default size, e.g. its CLI `--num-docs` default), then time each phase with `time.perf_counter()`. Use the same inputs the task's tests are likely to use: the baseline's own generator/loader and seed.
   - `parallel_fraction` = (time in work that is independent per item) / (total time of the target function), measured on the baseline as it is. The plan reports the resulting Amdahl bound as "parallelism alone", before any algorithmic fixes.
   - Peak memory: `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss`. It is KB on Linux and bytes on macOS. `tracemalloc` gives per-line allocation statistics.
4. **Measure a per-item cost proxy for every item** (e.g. `len(text)` per document, rows per file, bytes per request): one number per work item, in input order. Use a random sample of 20000 items if there are more. Also compute `weight_stats`: `cv` (stdev/mean), `max_over_median`, and `max_share` (largest item / total). The classify step uses them.
5. Do not modify the baseline files unless the task says to.

Answer with this JSON (merge over the state):

```json
{{
  "requirements": {{
    "deliverable_path": "<absolute path of the file to create/modify>",
    "required_api": ["<exact signature 1>", "<exact signature 2>"],
    "worker_counts": [1, 2, 4],
    "min_speedup": null,
    "correctness": "<what must match the baseline and how strictly>",
    "must_parallelize": true,
    "memory_limit_mb": null,
    "test_hints": "<anything the task says about how it will be tested: sizes, queries, timeouts>"
  }},
  "workload": {{
    "num_items": 0,
    "item_weights": [],
    "baseline_seconds": 0.0,
    "phase_seconds": {{"<phase>": 0.0}},
    "weight_stats": {{"cv": 0.0, "max_over_median": 0.0, "max_share": 0.0}},
    "parallel_fraction": 0.0,
    "peak_memory_mb": 0.0
  }}
}}
```

`min_speedup` may be a number or an object keyed by worker count (e.g. `{{"4": 2.0}}`). Use `null` when the task gives no number.
