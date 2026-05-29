---
name: memory-optimization
description: Optimize Python code for reduced memory usage and improved memory efficiency. Use when asked to reduce memory footprint, fix memory leaks, optimize data structures for memory, handle large datasets efficiently, or diagnose memory issues. Covers object sizing, generator patterns, efficient data structures, and memory profiling strategies.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
compatibility: "Requires Python 3.10+ and pandas. Optional: numpy, scipy.sparse, pympler, memory_profiler, ijson."
---

```yaml
purpose: >
  Transform Python code to minimize memory usage while preserving correctness.
  Covers per-object sizing (`__slots__`, namedtuple, dataclass), lazy iteration
  (generators, chunked I/O, memory-mapped files), dense→sparse and AoS→SoA
  layout shifts, string interning / categorical encoding, leak diagnosis
  (cycles, unbounded caches, closures), and profiling-driven verification.
  Apply when memory is the bottleneck — not as a default cleanup pass — and
  always verify a measurable reduction without correctness regression.

trigger_when:
  - User asks to reduce memory footprint, RSS, or peak allocation.
  - Code OOMs, swaps, or hits a per-process memory cap (multiprocessing workers, container limits).
  - Diagnosing a memory leak (RSS grows unbounded, GC pauses lengthen, cache never frees).
  - Loading datasets larger than RAM (CSV / Parquet / JSON / binary).
  - Building millions of small objects (records, points, particles, tokens).
  - Storing many repeated strings (status codes, enums, categorical columns).
  - Multiprocessing fanout duplicates large structures per worker.
  - Preparing data structures for sharing across processes (shared memory, memmap, sparse).

do_not_use_when:
  - CPU is the bottleneck and memory is comfortable — reach for the parallelization or algorithmic-complexity skills instead.
  - The change would obscure correctness for <10% RSS savings on a small dataset.
  - The dataset is already small (<100 MB) and the code is straightforward — premature optimization hurts readability without payoff.

scope_and_approval: >
  Read-only diagnosis (profiling, sizing, leak detection) is free to run.
  Code transformations rewrite the user's source — show the diff before
  applying when changes touch public APIs, on-disk formats, or shared
  modules. Explicit `gc.collect()` calls and forced eviction of caches
  alter runtime behavior beyond memory; flag them in the summary.

steps:
  - name: profile
    description: >
      Measure before optimizing. Identify the largest allocations, the hottest
      lines, and whether the symptom is steady high RSS (sizing problem) or
      monotonically growing RSS (leak). Useful tools, by job:
        - `sys.getsizeof(obj)` — shallow size of one object.
        - `pympler.asizeof.asizeof(obj)` — deep size including references.
        - `memory_profiler` `@profile` decorator — line-by-line RSS for a function.
        - `tracemalloc.start()` + `take_snapshot().statistics('lineno')` — allocation tracking with stack attribution.
        - `gc.get_objects()` + type histogram — count objects per class to find unbounded growth.
      Capture a baseline number (peak RSS or total allocated bytes) so the
      `verify` step has something to compare against.
    outputs:
      - name: baseline_memory
        type: object
        description: "Keys at minimum: peak_bytes, top_allocations (list of {file, line, bytes}), symptom in {'steady-high','growing'}."
      - name: hot_paths
        type: list[object]
        description: Functions or modules responsible for the largest allocations or leak growth.

  - name: analyze
    description: >
      For each hot path, classify the data structure and lifecycle. Look for
      these well-known leak shapes and their fixes:

        | Pattern              | Cause                                | Fix |
        |----------------------|--------------------------------------|-----|
        | Growing cache        | No eviction policy                   | `@lru_cache(maxsize=N)` or bounded dict |
        | Event listeners      | Not unregistered                     | `weakref` callbacks or explicit removal |
        | Circular references  | Objects reference each other         | `weakref`, break cycles, `gc.collect()` |
        | Global lists         | Append without cleanup               | bounded `deque(maxlen=N)`, periodic clear |
        | Closures             | Capture large enclosing objects      | Capture only the values you need |

      Decide whether the dominant cost is **per-instance overhead**
      (millions of small objects), **eager materialization** (lists built
      before consumption), **dtype overhead** (NumPy/Pandas at default
      widths), or **shared structure** that every worker duplicates.
    inputs:
      - name: baseline_memory
        type: object
      - name: hot_paths
        type: list[object]
    outputs:
      - name: bottleneck_class
        type: string
        description: One of {per_instance_overhead, eager_materialization, dtype_overhead, leak_cycle, leak_unbounded_cache, shared_structure_duplication, large_strings}.
      - name: target_paths
        type: list[object]
        description: The specific functions / modules / dataframes to transform.

  - name: select-strategy
    description: >
      Pick the optimization strategy by walking the decision tree against
      `bottleneck_class`:

        Large collections:
          - List of similar objects     → `__slots__`, `namedtuple`, or `@dataclass(slots=True)`
          - List built all at once      → generator / `yield from` / iterator
          - Storing repeated strings    → `sys.intern`, pandas `category`
          - Numeric data                → NumPy array instead of Python list

        Data processing:
          - Loading full file           → chunked reads (`pd.read_csv(chunksize=...)`), `mmap`, `np.memmap`
          - Intermediate copies         → in-place ops, NumPy views, `df.loc[...] = ...`
          - Keeping processed data      → process-and-discard, generator pipeline
          - DataFrame at default dtypes → run `scripts/optimize_dtypes.py` (downcast + categorical)

        Object lifecycle:
          - Objects never freed         → check circular refs, switch to `weakref`
          - Cache growing unbounded     → `@lru_cache(maxsize=N)`
          - Global accumulation         → explicit cleanup, context managers
          - Large temporaries           → `del` + `gc.collect()` at scope exit

      Per-item budget reference (use to estimate gain before transforming):

        | Structure                  | Memory per item     | Use case |
        |----------------------------|---------------------|----------|
        | `list` of `dict`           | ~400+ bytes         | Flexible, small datasets |
        | `list` of class            | ~300 bytes          | Object-oriented, small |
        | `list` of `__slots__` class| ~120 bytes          | Many similar objects |
        | `namedtuple`               | ~80 bytes           | Immutable records |
        | `numpy.ndarray` (float64)  | 8 bytes             | Numeric, vectorized ops |
        | `pandas.DataFrame`         | ~10–50 bytes / cell | Tabular, analysis |

      If the bottleneck doesn't fit any inline pattern (object-pool, weak-cache,
      copy-on-write, AoS→SoA, flyweight, sparse, streaming JSON, scoped
      cleanup, `StringIO` accumulation), consult
      `references/advanced_techniques.md` for ready-to-adapt templates.
    inputs:
      - name: bottleneck_class
        type: string
      - name: target_paths
        type: list[object]
    outputs:
      - name: chosen_patterns
        type: list[object]
        description: One entry per target path with the pattern name and a short rationale.

  - name: transform
    description: >
      Apply the chosen patterns. Templates for the six most common:

      **Pattern 1 — Class to `__slots__`** (40–60% per-instance reduction):

          class Point:
              __slots__ = ('x', 'y', 'z')
              def __init__(self, x, y, z):
                  self.x, self.y, self.z = x, y, z

      **Pattern 2 — List to generator** (avoid materialization):

          def get_all_records(files):
              for f in files:
                  yield from parse_file(f)
          for record in get_all_records(files):
              process(record)

      **Pattern 3 — Downcast NumPy / Pandas dtypes** (2–8× DataFrame reduction).
      Run `scripts/optimize_dtypes.py <input>` — it downcasts int64/float64
      to the smallest safe width, converts low-cardinality object columns to
      `category`, and demotes integral floats to nullable `Int64`. Import
      `optimize_dataframe(df)` from the same script when applying inline.

      **Pattern 4 — String dedup / interning** (for many repeated strings):

          import sys
          STATUS_ACTIVE = sys.intern('active')
          records = [{'status': STATUS_ACTIVE, ...} for _ in range(N)]

      Or for pandas:

          df['status'] = df['status'].astype('category')

      **Pattern 5 — Memory-mapped files** (data larger than RAM):

          import mmap
          with open('large_file.bin', 'rb') as f:
              mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
          arr = np.memmap('large_array.dat', dtype='float32', mode='r', shape=(N, D))

      **Pattern 6 — Chunked DataFrame processing**:

          def process_large_csv(path, chunksize=10_000):
              results = []
              for chunk in pd.read_csv(path, chunksize=chunksize):
                  results.append(process_chunk(chunk))
                  del chunk
              return pd.concat(results)

      For object pools, weak caches, COW, AoS→SoA, flyweight, sparse matrices,
      streaming JSON via `ijson`, scoped `gc.collect()` via context manager,
      and `StringIO` accumulation, read
      `references/advanced_techniques.md` and adapt the template to the
      user's code.
    inputs:
      - name: chosen_patterns
        type: list[object]
      - name: target_paths
        type: list[object]
    outputs:
      - name: transformed_paths
        type: list[object]
        description: For each path, the new code (or diff) and the pattern applied.

  - name: optimize-dataframe-dtypes
    description: >
      Apply only when `chosen_patterns` includes pandas dtype downcasting.
      Deterministic rules — do not re-implement inline. CLI for one-shot
      reports; import for in-process use.
    script: scripts/optimize_dtypes.py
    inputs:
      - name: dataframe_or_path
        type: object
        description: "Either a `pd.DataFrame` (import path) or a file path to CSV/Parquet (CLI path)."
      - name: category_threshold
        type: float
        nullable: true
        description: Unique-ratio cutoff below which object columns become categorical. Default 0.5.
    outputs:
      - name: optimized_dataframe
        type: object
        nullable: true
        description: In-process return value when called via import.
      - name: dtype_report
        type: object
        description: "Keys: input, rows, before_bytes, after_bytes, reduction_ratio, dtypes_before, dtypes_after."

  - name: verify
    description: >
      Re-run the profiling step on the transformed code and compare against
      `baseline_memory`. Checklist:
        - Peak RSS / total allocated bytes is measurably lower.
        - Outputs are identical to the pre-transform run (run the project's
          tests, or diff a representative output sample).
        - No new leak: run the workload twice in a single process and confirm
          RSS returns to a stable baseline between runs.
        - Wall-clock is acceptable — generators can add iteration overhead,
          `__slots__` blocks dynamic attributes, categorical dtypes change
          comparison semantics. Surface these trade-offs to the user.
        - Code is still readable. If a pattern obscured intent for marginal
          savings, revert it.
      Report the before/after numbers and which patterns were applied.
    inputs:
      - name: transformed_paths
        type: list[object]
      - name: baseline_memory
        type: object
    outputs:
      - name: verification_report
        type: object
        description: "Keys: peak_before, peak_after, reduction_ratio, correctness_check, leak_check, perf_delta, patterns_applied."

modes:
  - name: diagnose-only
    body: >
      Run `profile` and `analyze` only. Produce `baseline_memory` and
      `bottleneck_class` and stop. Use when the user asks "where is my memory
      going?" without authorizing code changes.
  - name: full-optimization
    body: >
      Run the entire procedure end-to-end: profile → analyze → select →
      transform → optimize-dataframe-dtypes (if relevant) → verify. Default
      when the user asks to "reduce memory" or "fix this leak".
  - name: leak-hunt
    body: >
      Skew toward the leak-shape table in `analyze`. Use `tracemalloc` diffs
      between two snapshots taken at the same logical point in two iterations
      to identify what survived a cycle it shouldn't have. Skip dtype
      downcasting unless growing DataFrames are the leak source.

scenarios:
  - need: Multiprocessing workers each duplicate a 2 GB inverted index.
    context: "Per-worker RSS scales linearly with worker count; bottleneck_class = shared_structure_duplication."
    action: "Move the index into np.memmap (or multiprocessing.shared_memory.SharedMemory); workers attach read-only. Apply pattern 5; verify per-worker RSS drops to near-zero overhead."
    outcome: "Total RSS becomes O(index) + O(workers · per-worker working set), not O(workers · index)."

  - need: List of 5 million dict records consumes 3 GB.
    context: "bottleneck_class = per_instance_overhead; records have a fixed schema."
    action: "Convert to @dataclass(slots=True) or namedtuple (pattern 1); if the records are numeric and bulk-processed, convert to a struct-of-arrays NumPy layout (see references/advanced_techniques.md AoS→SoA)."
    outcome: "2–4× reduction in per-record bytes; vectorized ops become available if SoA was chosen."

  - need: "pd.read_csv produces a 1.5 GB DataFrame at default dtypes."
    context: "bottleneck_class = dtype_overhead; columns are mostly small ints, repeated category strings, and a few floats with NaN."
    action: "Run scripts/optimize_dtypes.py data.csv. Inspect dtype_report.reduction_ratio. If a column needed manual handling (e.g., timestamp parsing), patch it after the mechanical pass."
    outcome: "Typical 2–8× reduction with no code change downstream; categorical columns also speed up groupby."

  - need: RSS grows by ~50 MB on every request loop.
    context: "bottleneck_class = leak_unbounded_cache or leak_cycle; tracemalloc between iterations attributes growth to a single module."
    action: "If a cache, bound it with @lru_cache(maxsize=N) or switch to WeakValueDictionary (see references/advanced_techniques.md). If circular refs, break the cycle or replace one side with weakref.ref."
    outcome: "RSS stabilizes after a warmup; no growth across iterations."

  - need: Building a 100 MB string by += concatenation is slow and uses ~10 GB.
    context: "O(n²) memory from repeated string copies."
    action: "Replace with ''.join(chunks); for streaming, write to io.StringIO and call getvalue() once (see advanced techniques)."
    outcome: "Memory drops to O(n); wall-clock typically improves order-of-magnitude."

anti_patterns:
  - Optimizing without profiling. Measure first; the suspected bottleneck is often not the real one.
  - Applying `__slots__` to classes you have <1000 instances of — the savings are noise, you lose dynamic attributes and multiple inheritance flexibility.
  - Replacing a list with a generator that gets consumed twice. Generators are one-shot; if the caller iterates twice, you reintroduced the materialization cost or worse, silently returned empty the second time.
  - Calling `gc.collect()` in a hot loop. It pauses execution; use only at scope boundaries (e.g., inside a context manager that owns a large temporary).
  - Downcasting dtypes before checking value ranges. `int64` → `int8` silently overflows; the script in this skill uses `pd.to_numeric(downcast=...)` which checks bounds — do not bypass it with a raw `astype`.
  - Interning user-supplied strings without bounds. `sys.intern` keeps strings alive for the process lifetime; interning unbounded user input is itself a leak.
  - Converting an object column to `category` when cardinality is high (>50% unique). Category overhead exceeds the savings; the script's threshold guards against this.
  - Reaching for sparse matrices without checking density. Sparse formats only win below ~10% density; above that they're slower and larger than dense.
  - Treating memory wins as free. Generators add per-item overhead; categorical dtypes change comparison semantics; `__slots__` blocks `__dict__`. Always confirm wall-clock and semantics in `verify`.
  - Skipping the leak re-run check. A one-shot RSS measurement can look better while the leak rate is unchanged — run the workload twice and confirm RSS returns to baseline.
```
