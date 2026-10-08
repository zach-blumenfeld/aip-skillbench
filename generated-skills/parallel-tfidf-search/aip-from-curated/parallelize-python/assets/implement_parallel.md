# Implement the parallel version

Task statement:

{task}

Requirements (from characterize): {requirements}

Plan (from `plan_strategy.py`; follow it unless a measurement proves it wrong):

{plan}

Runtime probe (CPUs, start methods, available packages): {analysis}

Workflow. Work through every item; each one prevents a known failure.

1. **Algorithmic fixes first** (`plan.algorithmic_fixes_first`). Rewrite O(n×m) passes as single linear passes in the new code, e.g. per-term document frequencies counted from each item's term set in one pass rather than rescanning every item for every term. Do this before tuning workers: parallelizing a quadratic loop only divides it by W.
2. **Write the deliverable** at `requirements.deliverable_path` with exactly the API in `requirements.required_api`: names, parameter names, defaults, and return types identical to the baseline's counterparts. Import and reuse the baseline's helpers and data classes instead of copying them. Shared helpers keep per-item results bit-identical, and the tests compare against the baseline's types.
3. **Executor**: `plan.executor`. Use only packages the probe reports as importable. Worker functions are module-level (picklable). Bound the pool at `num_workers`. Use the pool as a context manager. Accept `num_workers=None` meaning `os.cpu_count()`, capped at the number of items.
4. **Distribution**: `plan.balancing` and `plan.best_balance`. Use the simplest strategy that comes in under the imbalance target at the task's worker counts. For each worker count W, use `plan.best_balance[W]`, which gives the strategy and the number of chunks. LPT chunk packing is capped at total cost / largest item, so one giant item never overfills a chunk. If no partition is under target, split the largest items into subtasks. When the required API has a `chunk_size` parameter, treat it as a maximum number of items per chunk. Send each worker only the fields it needs.
5. **Large read-only inputs** (an index, a model, a corpus): `plan.shared_input`. Pick the start method explicitly, because Python 3.14+ and macOS default to spawn/forkserver, which do not inherit globals.
6. **Merge** partial results in the parent in one linear pass. Keep the baseline's item order wherever order can affect floats or tie-breaks (`plan.exactness`).
7. **Fast path**: for `num_workers == 1`, or inputs too small to amortize starting a pool (with `num_workers=None` too), run in-process with the same (fixed) algorithm, so the new code is never slower than the baseline.
8. **Verify by measurement, not inspection.** Copy the harness below into a scratch directory outside the deliverable folder and fill in its marked parts. Run it on the task's input sizes at every worker count in `requirements.worker_counts`. Time **each public function separately** (`FUNCTIONS`; set `PRIMARY` to the one the task's threshold names). Compare full outputs against the sequential baseline on the same input. Time both, best of 3 after one warm-up. Get the load imbalance, straggler ratio and utilization from `measure_chunk_costs` over the deliverable's own chunks. Run with `PYTHONDONTWRITEBYTECODE=1` and remove any `__pycache__` that lands in the deliverable folder. If the task states no numbers, also run it on a second, smaller input to make sure the small-input path works.
9. Walk `plan.verification_checklist` and record each item as true/false.

Harness template (`assets/harness_template.py`):

```python
{assets[harness_template]}
```

Load `references/parallel-patterns.md` for executor code patterns, `references/balancing-strategies.md` for partitioning and straggler code, and `references/memory-patterns.md` when memory is a concern. Load `references/map-reduce-index.md` when the workload builds an index, vocabulary, histogram or other global aggregate from per-item data (TF-IDF, inverted index, word counts), or batch-scores queries against such an index.

Answer with this JSON:

```json
{{
  "deliverable_path": "<absolute path written>",
  "verification": {{
    "outputs_match": true,
    "comparison_detail": "<what was compared, on which inputs, tolerance>",
    "api_ok": true,
    "api_detail": "<signatures checked>",
    "timings": {{"sequential_seconds": 0.0, "parallel_seconds": {{"1": 0.0, "4": 0.0}}}},
    "speedups": {{"1": 0.0, "4": 0.0}},
    "per_function": {{"<function>": {{"speedups": {{"4": 0.0}}, "min_speedup": null}}}},
    "load_imbalance": null,
    "straggler_ratio": null,
    "worker_utilization": null,
    "peak_memory_mb": null,
    "baseline_peak_memory_mb": null,
    "errors": [],
    "checklist": {{"<checklist item>": true}}
  }}
}}
```
