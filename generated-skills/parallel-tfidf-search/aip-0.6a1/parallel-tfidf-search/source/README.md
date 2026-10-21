# Source: parallel-tfidf-search

## Provenance

Compiled on 2026-10-20 into one AIP 0.6a1 skill from:

| File | Origin |
|---|---|
| `python-parallelization/SKILL.md`, `references/advanced_techniques.md` | curated skill, verbatim |
| `workload-balancing/SKILL.md`, `references/advanced_techniques.md` | curated skill, verbatim |
| `memory-optimization/SKILL.md`, `references/advanced_techniques.md` | curated skill, verbatim |
| `task-instruction.md` | the task statement the downstream agent receives, verbatim |

The task's environment (`sequential.py`, `document_generator.py`, Dockerfile `python:3.12-slim`,
standard library only) was read to build and test the template; it is not copied here because it
is task input, not skill material.

## Intent

The three skills describe one workflow: classify the workload, pick a parallel strategy,
balance the work, keep memory lean, verify correctness and speedup. Applied to the TF-IDF task
that becomes: inspect the baseline → install (or adapt) a tested parallel implementation →
verify exact equality and the 1.5x / 2x speedup targets → fix if anything fails.

## Component-kind choices

| Step | Kind | Why |
|---|---|---|
| `inspect` | execution | Checking names, signatures, dataclass fields and formula fingerprints in the baseline is deterministic (AST + regex); so is reading CPU count and start methods. It emits `plan`, so the branch is a rule, not a judgment. |
| `by-plan` | router | Branches on the script's `plan` (`template` / `adapt`). |
| `install` | execution | Writing the known-good template is mechanical; the template content is passed as an asset. |
| `adapt` | client_task | Rewriting code for an unforeseen baseline variant is generation; the template and deviations are given as context. |
| `verify` | execution | API shape, `==` comparison of index and results, and timing are all scriptable; the speedup targets (1.5x, 2.0x) are thresholds in code. |
| `by-verdict` | router | Branches on `verdict` (`pass` / `fail`). |
| `fix` | client_task | Diagnosing and editing code is generation; the template lists failure types and their usual causes. |

No decision step: every branch point in this workflow is decided by a rule over script output.
A `hardware_limited` verdict was considered and folded into the fix guidance (report the CPU cap
rather than fake a pass) because it cannot be distinguished from a slow solution without judgment.

Implementation choices baked into `assets/parallel_solution.py` (all measured):
- Processes, not threads (CPU-bound, GIL). Fork context when available so documents/index are
  inherited copy-on-write; spawn fallback through an initializer (tested: identical results).
- Index map step = tokenize + TF per contiguous chunk of `chunk_size` documents via ordered `imap`
  (dynamic pull balances the log-normal document lengths); one-pass merge in document order
  replaces the baseline's vocabulary × documents scans.
- Search = `_score_query` per query in workers, ~4 chunks per worker, `(doc_id, score)` returned,
  titles attached once in the parent. `_score_query` accumulates products from posting lists and
  sums them with builtin `sum()` (a first try with `acc += x` mismatched: Python 3.12+ `sum()` is
  compensated). Stress test: 0 mismatches over 8,400 queries on 3 corpora, top_k 1/10/50, on
  Python 3.12 and 3.14. ~2.8x less work per query than the baseline.
- The first version called the baseline's `search_sequential` in workers: correct, but only
  ~2x at 50 queries because of ~40–50 ms pool start-up; the faster scorer restores margin.

## Where source content lives in the skill

- Decision trees, candidate table, safety rules, pitfalls, verification checklists of all three
  skills → `references/parallelization-playbook.md` (§3 parallelization, §4 balancing, §5 memory,
  §6 checklist) and the procedure's `anti_patterns`.
- The three `advanced_techniques.md` files → mirrored verbatim as
  `references/{python-parallelization,workload-balancing,memory-optimization}-advanced.md`,
  loaded on demand from the `adapt`/`fix` steps.
- Workflows (analyze/classify/select/transform/verify; characterize/identify/select/implement/monitor;
  profile/analyze/select/transform/verify) → the step graph itself plus the playbook.

## Deliberate-drop log

| Dropped | Rationale |
|---|---|
| python-parallelization Pattern 2 (requests → aiohttp), Pattern 4 (hybrid asyncio + process pool) code | I/O-bound patterns; this workload is CPU-bound. The decision-tree branches naming them are kept in the playbook; full code stays available in `source/` and the mirrored advanced reference. |
| python-parallelization Pattern 3 (nested loops → `np.outer`) code | Requires NumPy, absent from the container; the "vectorize numeric loops" rule is kept in the playbook. |
| python-parallelization Pattern 1 code (loop → ProcessPoolExecutor) as a separate snippet | Embodied, with the task's specifics, in `assets/parallel_solution.py`. |
| workload-balancing Strategy 1–5 code (static `np.array_split`, dynamic `wait(FIRST_COMPLETED)` queue, async work-stealing pool, weighted greedy partition, async semaphore) | The chosen strategy (ordered dynamic `imap` over contiguous chunks) is implemented in the template; the others are summarized with when-to-use in playbook §4. The semaphore strategy is I/O-only. Code remains in `source/`. |
| workload-balancing straggler code (timeouts, speculative execution, rebalancing) | Not needed once chunks are pulled dynamically; the techniques are named in playbook §4. |
| memory-optimization Patterns 1–6 code (slots, generator, pandas downcast, interning, mmap/np.memmap, chunked CSV) | Generic techniques the agent knows; pandas/NumPy absent in the container. Each is named in the playbook §5 decision tree. |
| memory-optimization profiling snippets for `pympler` / `memory_profiler` | Not installed in the container; `tracemalloc` and `sys.getsizeof` are kept. |
| Frontmatter descriptions of the three skills | Superseded by this skill's own description and `trigger_when`. |

## Functional test log (2026-10-20, `aip run`, local Python 3.14; scripts also run on 3.12)

| Run | Workspace | Path | Result |
|---|---|---|---|
| 1 | real task files | inspect → template → install → verify → **pass** → end | index 3.63x, search 3.23x (5,000 docs, 300 queries, 4 workers) |
| 2 | variant: smoothed IDF `log((N+1)/(df+1)) + 1` | inspect → **adapt** (changed the IDF line) → verify → pass → end | index 3.22x, search 5.46x |
| 3 | variant: baseline keeps the first 8 query tokens | inspect → template → install → verify → **fail** → **fix** (mirrored `[:8]`) → end | re-verified pass, index 2.45x, search 3.92x |
| extra | real files, 1,000 docs / 30 queries | template → pass | index 1.8x, search 2.98x (adaptive in-process guard) |

Findings fed back into the skill:
- Run 3 first passed by mistake: the verifier had no query longer than 8 content terms. It now
  generates long passages and repeated-term queries as well; rerun caught the mismatch.
- Afterwards `inspect` gained fingerprints for unmodified query tokenization and untruncated
  posting lists, so that variant is now routed to `adapt` up front (checked: the real files still
  route to `template`).
- `fix.md` now starts search mismatches with a line-by-line diff of `search_sequential` against
  `_score_query`.
- Limitation: on the fix path the end state's `verdict` is the first verification; the fix
  step's `final_verdict` holds the re-verification (a key may have only one producer).
- The task's Docker image was not built (that would write outside the allowed folders); Linux
  `fork` is cheaper than macOS, so container start-up overhead should be no worse than measured here.
