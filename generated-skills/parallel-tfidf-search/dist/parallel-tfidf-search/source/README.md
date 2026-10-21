# Provenance and compilation notes: parallel-tfidf-search

## Sources (copied verbatim into this folder)

| Path | Origin |
|---|---|
| `python-parallelization/SKILL.md`, `python-parallelization/references/advanced_techniques.md` | curated skill "python-parallelization" |
| `workload-balancing/SKILL.md`, `workload-balancing/references/advanced_techniques.md` | curated skill "workload-balancing" |
| `memory-optimization/SKILL.md`, `memory-optimization/references/advanced_techniques.md` | curated skill "memory-optimization" |

Task context used (not copied; it lives in the task container): the task statement
(parallelize `/root/workspace/sequential.py` into `parallel_solution.py` with
`build_tfidf_index_parallel` and `batch_search_parallel`, 1.5x index / 2x search at 4
workers, identical results), the baseline `sequential.py`, `document_generator.py`,
and the `python:3.12-slim` Dockerfile (stdlib only, no numpy).

## Intent

The three sources are generic. The target workflow is one concrete task family:
make a pure-Python TF-IDF engine multi-process with bit-identical output. The skill
therefore ships a tested implementation plus an exact-equality verifier. The
generic knowledge goes into `references/parallelization-playbook.md` for the
adaptation and diagnosis branches.

Facts measured while building this (5,000-doc corpus from `generate_corpus(5000, seed=42)`, 392 terms):
- Sequential index: 9.7–14.5 s. About 6 s is tokenize+TF; the rest is the
  O(V×D) DF and posting scans.
- Sequential search: 6–17 ms per 3-term query, up to about 50 ms for mixed queries.
- Pickled index plus documents: 32 MB (1.1 s to pickle, 0.6 s to unpickle).
- Template on 4 workers: fork gives 4.3–4.5x index and 3.9x search; spawn gives 4.3x
  index and 0.99x search (index re-pickled per worker), 1.62x after pickling once.
- Machine load swung the absolute times about 10x between runs (sequential index
  0.6–14.5 s); ratios are what count. In a quiet run on a 5,000-doc corpus inside
  the verifier: sequential index 0.83–0.88 s, tokenize ~0.4 s, single-pass assemble
  ~0.16 s (a third of it the posting sorts).
- CPython's cyclic GC re-scanning the caller's large heap made the baseline search 5x
  slower inside the verifier. Adding `gc.freeze()` in workers and pausing GC during
  result unpickling and assembly took the template to 3.0–3.2x index and 2.9–3.2x
  search (fork, 4 workers); before, a run showed 1.59x index.
- A re-implemented `+=` dot product drifted by about 1e-16 (functional test); the
  verifier labels this "float drift only".
- Python 3.12 `sum()` uses compensated summation, so any re-implemented dot product
  drifts in the last bits. Workers must call `search_sequential`.

## Component-kind choices

| Component | Kind | Why |
|---|---|---|
| Environment check (Python version, CPU count, start methods) | execution (one-liner) | deterministic facts |
| Parallel implementation (`scripts/parallel_solution.py`) | execution (template copied into place) | the transformation is fully codable over the declared inputs; a tested template removes the main failure modes (tie order, float drift, pickling the index) |
| `baseline_variant` | decision (choice) | judging whether a given `sequential.py` matches the template's assumptions requires reading code; the answer space is fixed and routes the next step |
| Adapt template when the baseline differs | client task | needs code generation specific to the unseen baseline |
| Preflight, equality and speed checks (`scripts/verify_parallel.py`) | execution | validation against fixed rules (exact equality of 7 fields, signatures/defaults, speedup thresholds 1.5/2.0) and the edge-case matrix are deterministic; exit codes 0/1/2 drive branching |
| Exit-code routing | prose over script output | deterministic mapping of a structured script result to the next step |
| `speed_miss_cause` | decision (choice) | needs judgment over the summary plus a rerun (noise vs hardware vs code); fixed answer set with an action per label |
| Fix after a mismatch or a slow implementation | client task | code edits |
| Final report | client task | text synthesis |

Thresholds kept as code: in-process cut-offs (`MIN_DOCS_FOR_POOL = 64`, measured
break-even under fork; `MIN_QUERIES_FOR_POOL = 4`; `MIN_SEARCH_WORK_FOR_POOL = 50,000`
query×doc pairs ≈ 0.1 s of search, the source's over-parallelization rule made concrete), `CHUNKS_PER_WORKER = 4`, and the
speedup targets as verifier defaults. Load-balance monitoring targets (imbalance
< 1.2, straggler < 2.0, utilization > 90%) stay as diagnostic criteria in the
`implementation` branch. The template does not instrument per-worker times, because
that would add overhead to timed code.

## Where each source item landed

- python-parallelization: workflow → playbook §1 and the body procedure; decision
  tree and candidate table → playbook §2 (the CPU-bound → processes choice is applied
  in the template and the "threads do not help" gotcha); patterns 1 and 4 → playbook §2;
  safety requirements → playbook §2 and the template (ordered `imap`, bounded workers,
  context-managed pools, worker exceptions re-raise through `imap`); pitfalls → body
  Gotchas and playbook §2; verification checklist → `verify_parallel.py` and playbook §5.
- workload-balancing: workflow, decision tree, strategies 1–5, partitioning table,
  stragglers, monitoring metrics, anti-patterns, checklist → playbook §3; the
  dynamic-scheduling choice (small ordered chunks for log-normal lengths) → template
  and Gotchas; metrics → `speed_miss_cause` / `implementation` action.
- memory-optimization: workflow → playbook §1; decision tree, patterns 1–6, size
  table, leak table, profiling → playbook §4; "send the minimum / don't copy the index
  per task" → template and Gotchas; verification items → playbook §5.
- All three `advanced_techniques.md` → playbook §6 (one row per pattern, with key
  parameters such as virtual nodes 100, circuit breaker 5 failures / 30 s, adaptive
  batching 100/10/10000 with 1.1x/0.9x triggers, backoff base·2^n with full jitter
  and 5 tries).

## Deliberate-drop log

| Dropped | Rationale |
|---|---|
| Verbatim code bodies of I/O, async, pandas, numpy, numba, dask, and distributed-systems examples (aiohttp fetch, `np.outer`, `optimize_dtypes`, `WorkStealingPool`, `ConsistentHash`, `CircuitBreaker`, `RateLimitedQueue`, etc.) | They do not apply to a CPU-bound, stdlib-only TF-IDF task. Each is kept as a one-line pattern with its key parameters in playbook §6 and verbatim in `source/`. |
| Straggler timeouts with fallback values and speculative re-execution as *implementation* choices | A fallback value or a cancelled task would break the "identical results" requirement, and TF-IDF tasks are deterministic. They are kept as knowledge in playbook §3 but not used in the template. |
| Source frontmatter descriptions and one-line intros ("Transform sequential Python code ...") | Background, superseded by this skill's description and Purpose. |
| Memory per-structure byte figures as decision inputs | Kept as reference numbers in playbook §4; no threshold in this task depends on them. |
