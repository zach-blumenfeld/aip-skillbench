---
name: parallel-tfidf-search
description: Parallelize a sequential Python TF-IDF search engine (inverted-index building plus cosine-similarity batch search) with multiprocessing so it hits multi-core speedup targets while producing bit-identical results to the baseline. Use when asked to write parallel_solution.py with build_tfidf_index_parallel / batch_search_parallel, speed up sequential.py's TF-IDF indexing or querying, or parallelize any CPU-bound pure-Python document-processing pipeline whose output must match the original exactly. Ships a drop-in template, a verifier that checks exact equality and measures speedups, and load-balancing and memory guidance.
compatibility: Python >= 3.9 (task container is python:3.12-slim). Standard library only (multiprocessing, pickle, inspect, json, math, random). No pip packages. Linux uses the fork start method; other platforms fall back to spawn.
---

# Parallel TF-IDF Search

## Trigger When

- The task asks for a parallel solution file (e.g. `/root/workspace/parallel_solution.py`) with `build_tfidf_index_parallel(documents, num_workers=None, chunk_size=500)` and `batch_search_parallel(queries, index, top_k=10, num_workers=None, documents=None)`.
- A sequential TF-IDF / inverted-index / cosine-similarity engine (a `sequential` module plus a `document_generator` module) must use idle cores, with targets such as 1.5x indexing and 2x search speedup at 4 workers.
- Output must be "identical to the original" while running in parallel.
- More broadly: converting a CPU-bound pure-Python loop over documents or queries to multiprocessing, balancing skewed document lengths across workers, or keeping parallel float results bit-exact.

## Purpose

Turn the single-threaded TF-IDF baseline into a multi-process version that returns the same `TFIDFIndex` and the same `SearchResult` lists, down to the last float bit and tie order. It meets the speedup targets by parallelizing the per-document tokenization, replacing the baseline's O(vocabulary × documents) loops with one pass, and fanning queries out to forked workers. It adds what general parallelization advice misses: which baseline functions must be reused verbatim, the tie-order and float-summation traps, how to ship a large index to workers, and a verifier that proves equality and measures speedups.

## Gotchas

- **Reuse the baseline's own functions.** Import `tokenize`, `compute_term_frequencies`, `TFIDFIndex`, `SearchResult`, `IndexingResult` and `search_sequential` from the baseline module `sequential`; do not re-implement them. The tests compare against these exact objects.
- **Do not rewrite the cosine dot product.** Python ≥ 3.12 `sum()` over floats uses compensated (Neumaier) summation, so `+=` accumulation or `math.fsum` gives scores that differ in the last bits. Workers call `search_sequential` itself.
- **Top-k tie order** comes from `heapq.nlargest` over the iteration order of the candidate `set`. Re-implementing candidate collection or scoring order can reorder equal-score documents. Calling `search_sequential` keeps the order.
- **Posting-list order**: the baseline appends `(doc_id, tfidf)` in document order, then calls `list.sort(key=lambda x: x[1], reverse=True)`, which is stable. Build postings in the same document order and sort on the same key with `reverse=True` (the template uses the equivalent, faster `itemgetter(1)`). Never `imap_unordered` or reorder documents before assembly.
- **Norms**: accumulate `norm_squared += tfidf * tfidf` in the doc's term-frequency dict order (first occurrence in the text), not with `sum()`.
- **Where the index time goes**: about 40–60% is tokenization (parallelized), and the rest is the baseline's per-term scan over all documents for DF and postings (replaced by the single pass, about 0.16 s for 5,000 docs). Measured with 4 workers: about 3x.
- **Shipping the index**: about 32 MB pickled for 5,000 docs. On Linux use the `fork` context so workers inherit it copy-on-write. Under spawn/forkserver, pickle it **once** to bytes and pass it through the pool initializer. Passing objects as `initargs` re-pickles them serially per worker, and per-task pickling is far worse; both erase the search speedup (measured 0.99x).
- **The cyclic GC is a hidden serial cost.** The caller's heap (corpus, indexes) holds millions of objects, and every automatic full collection re-scans it. Measured: baseline search ran 5x slower inside the verifier's large heap. The template calls `gc.freeze()` in each worker initializer and pauses GC while the parent unpickles results and assembles the index. Results are unchanged (no reference cycles are created). Keep this when editing.
- **Threads do not help**: this is CPU-bound pure Python (GIL). Use processes.
- **Load balance**: document lengths are log-normal (20 to 10,000 words). Treat `chunk_size` as an upper bound. Shrink chunks to about 4 per worker and feed them through ordered `Pool.imap`, so fast workers pull more work (dynamic scheduling).
- **Small inputs** run in-process: fewer than 64 docs, or a search batch under 4 queries or under 50,000 query×document pairs. They give the same results without pool start-up cost. Measure speedups on realistic sizes (thousands of docs, hundreds of queries).
- **Edge semantics to preserve**: an empty corpus gives an empty index. A doc with no tokens gets an empty vector and norm `0.0`, and search skips it. Duplicate `doc_id`s: last tf wins, but every copy's terms stay in the vocabulary. A query with no known terms returns `[]`.
- Worker functions must be module-level (picklable). The template adds its own directory to `sys.path` so spawned workers can import `sequential`.

## Procedure

Progress:
- [ ] 1. Check the environment (execution)
- [ ] 2. Classify the baseline (decision `baseline_variant`)
- [ ] 3. Install the template (execution); adapt it if step 2 says so (client task)
- [ ] 4. Verify correctness and speed (execution) → branch on the exit code
- [ ] 5. Report (client task)

Run every command from this skill's folder (where `scripts/` lives). The task workspace is `/root/workspace` and holds the baseline (`/root/workspace/sequential.py`) and its corpus generator (`/root/workspace/document_generator.py`). If the workspace is elsewhere, substitute its absolute path.

### 1. Check the environment (execution)

```bash
python3 --version && python3 -c "import multiprocessing as m, os; print(os.cpu_count(), m.get_all_start_methods())"
```

You need Python ≥ 3.9 and the standard library only. Name anything missing before continuing. Fewer than 4 CPUs means the 4-worker targets cannot be shown on this machine (see step 4).

### 2. Classify the baseline (decision)

Read the baseline in full: its `build_tfidf_index_sequential`, `search_sequential`, `tokenize`, `compute_term_frequencies` and the dataclasses. Then answer:

```yaml
baseline_variant:
  type: choice
  instructions: >
    Compare the baseline with the template's assumptions:
    text = title + " " + content; tokenize(); TF = count/total; DF = docs containing term;
    IDF = log(N/DF) + 1; postings (doc_id, tf*idf) in doc order, sorted by score desc;
    doc_vectors tf*idf with L2 norm; search = search_sequential over a TFIDFIndex with
    fields num_documents, vocabulary, document_frequencies, idf, inverted_index,
    doc_vectors, doc_norms. Which case applies?
  criteria:
    matches_template: Every assumption above holds (names, formulas, order, fields).
    index_math_differs: Same names and API, but index construction differs (other TF/IDF formula, extra smoothing, different text fields, extra index fields, different posting sort).
    api_differs: Required names, dataclass fields or function signatures differ, or search does not go through a single per-query function.
    other: The engine is not TF-IDF over an inverted index.
```

A false `matches_template` is the costly mistake: the verifier would catch it, but only after a full run. Reconsider any close call that leans toward `matches_template`.

### 3. Install the template (execution) and adapt (client task)

```bash
cp scripts/parallel_solution.py /root/workspace/parallel_solution.py
python3 scripts/verify_parallel.py --workspace /root/workspace --preflight-only
```

The preflight checks that the baseline names exist and that both parallel signatures and defaults match the task. Exit 0 means continue.

- `matches_template` → no edits; go to step 4.
- `index_math_differs` → **client task**: edit only `_assemble_index` (and `_tf_chunk` if the text fields differ) in `/root/workspace/parallel_solution.py`, mirroring the baseline's formula and iteration order. Keep the single-pass structure.
- `api_differs` → **client task**: change the imports and wrappers so each worker still calls the baseline's own per-document and per-query functions. Keep the return types: `ParallelIndexingResult` (subclass of the baseline's result, with `index`, `elapsed_time`, `num_documents`, `vocabulary_size`) and `(results, elapsed_time)`. Read [references/parallelization-playbook.md](references/parallelization-playbook.md) for patterns.
- `other` → **client task**: apply the playbook's workflow (profile → classify → partition → transform → verify) to the actual engine, using the template as the structural example. Run step 4 with the verifier adapted to the engine's API.

What the template does (keep these properties when editing):
- Index: `(doc_id, title, content)` tuples → chunks of `min(chunk_size, ceil(n ÷ (4·workers)))` → `Pool.imap(_tf_chunk)` in order → a single-pass reduce computing DF, IDF, doc vectors, norms and postings, then a stable sort.
- Search: queries split into about 4 chunks per worker. Under fork the index sits in a module global set before the pool is created; otherwise it is pickled once and passed through the initializer. Each worker runs `search_sequential`, and results are flattened in order.
- `num_workers=None` → `len(os.sched_getaffinity(0))` (falls back to `os.cpu_count()`). Elapsed times include pool start-up.

### 4. Verify (execution)

```bash
python3 scripts/verify_parallel.py --workspace /root/workspace --num-docs 3000 --workers 4
```

Generating documents is slow (2–20 s per 1,000 docs, depending on load). For reruns, save one corpus with `python3 /root/workspace/document_generator.py --num-docs 3000 --output /tmp/corpus.json` and pass `--corpus /tmp/corpus.json` instead of `--num-docs`. The verifier builds both indexes and compares all seven `TFIDFIndex` fields exactly. It also checks worker counts 1/None/4, a tiny `chunk_size`, a huge `chunk_size`, a 150-doc subset and an empty corpus. It searches 200 generated queries, including the empty-string, stop-words-only, unknown-term, punctuation, repeated-term, rare-term and long cases, and checks `documents=None`, `top_k=3` and batches of 0 and 2. The last line is `SUMMARY {json}` with `problems`, `index_speedup`, `search_speedup`, `cpu_limited` and `exit_code`.

Branch on the exit code:
- **0**: identical and both targets met → step 5.
- **1**: correctness or API failure. Each problem line names the field, path and kind: "float drift only" (|diff| ≤ 1e-9) means you changed arithmetic or summation order (see Gotchas); "values differ" means the formula or inputs differ from the baseline (revisit `baseline_variant`); "structural/order difference" means wrong keys, lengths, ids or ordering. **Client task**: fix `/root/workspace/parallel_solution.py` and rerun step 4. Never loosen the comparison.
- **2**: correct, but a target was missed. Answer `speed_miss_cause`, act, and rerun.

```yaml
speed_miss_cause:
  type: choice
  instructions: Using the SUMMARY (cpu_count, cpu_limited, seconds, speedups) and one rerun, why was a target missed?
  criteria:
    cpu_limited: cpu_limited is true or fewer than 4 CPUs are usable (container quota); the code cannot be faster than the hardware allows.
    workload_too_small: The sequential step took well under ~1 s (tiny corpus or few queries), so pool start-up dominates.
    noisy_timing: A rerun of the same command meets the target (machine was busy).
    not_fork: Platform start method is spawn/forkserver (non-Linux), so the index is shipped by pickling.
    implementation: None of the above; the parallel code itself is slow.
```

Actions: `cpu_limited` → keep the code and report the hardware limit with the measured numbers. `workload_too_small` → rerun with `--num-docs 3000` or more and `--num-queries 200` or more. `noisy_timing` → accept the passing rerun. `not_fork` → confirm on Linux if possible, otherwise report it. `implementation` → **client task**: check that nothing large is pickled per task, that chunks number about 4 per worker, that ordered `imap` is used, that the GC freeze/pause is still in place, and the playbook's monitoring targets (imbalance < 1.2, straggler ratio < 2.0, utilization > 90%), then fix and rerun. Reconsider a close call between `noisy_timing` and `implementation` by running once more.

### 5. Report (client task)

State the solution path, whether results were identical (and which checks ran), and the measured index and search speedups against the targets, with CPU count. Mention any branch taken in step 3 or step 4.

## Files

- `scripts/parallel_solution.py`: drop-in solution template (step 3). Run it directly for a demo: `python3 /root/workspace/parallel_solution.py --num-docs 500 --workers 4`.
- `scripts/verify_parallel.py`: preflight, exact-equality and speedup verifier (steps 3–4).
- [references/parallelization-playbook.md](references/parallelization-playbook.md): load only when adapting the template (step 3, non-`matches_template`) or diagnosing `implementation` in step 4. It covers decision trees for CPU/IO/data-parallel work, balancing strategies and metrics, memory techniques, checklists, and an index of advanced patterns.
- `source/`: the original skills this was compiled from, plus `source/README.md` (provenance, component choices, drop log).
