# Fix the parallel TF-IDF solution

Verification of `{solution_path}` (baseline in `{workspace_dir}`) failed:

{failures}

Measurements: {verification_report}

Diagnose by failure type, then edit `{solution_path}`:

- **Import / signature / return-type failure**: match the required API exactly:
  `build_tfidf_index_parallel(documents, num_workers=None, chunk_size=500)` returning
  `ParallelIndexingResult`; `batch_search_parallel(queries, index, top_k=10, num_workers=None, documents=None)`
  returning `(results, elapsed_time)`. `TFIDFIndex`, `SearchResult`, `IndexingResult` must be
  imported from `sequential`, never redefined (dataclass equality needs the same class).
- **Index differs**: compare the named field against the baseline. Usual causes: merging
  chunks out of order (`imap_unordered`, `as_completed`), a different float expression or
  summation order for TF-IDF or norms, DF counted per chunk with duplicate doc_ids, a
  re-implemented tokenizer.
- **Search differs**: diff the baseline's `search_sequential` against `_score_query` line by
  line first: any extra step there (query-token truncation or filtering, a different weight,
  boost, threshold or top-k rule) must be mirrored exactly. Look at which queries fail (long
  ones, repeated terms, titles) for a hint. Otherwise it is tie order or summation: the
  candidate set must be filled in the baseline's order and dot products summed with builtin
  `sum()` over the products in query-term order. If unsure, score each query with the
  baseline's own `search_sequential` in the worker (identical by construction, slower); titles must use `doc_titles.get(doc_id, f"Document <id>")`
  exactly as the baseline does, and `documents=None` must yield the default titles.
- **Speedup below target**: check the report's CPU count first (fewer CPUs than workers caps
  speedup: report it, do not fake it). Otherwise look for per-task pickling of the index or
  documents (publish them in a global before a fork pool), too few or too many chunks, the
  title map rebuilt per query, or pool creation repeated per item.
- **Exception during verification**: read the traceback; spawn-only platforms need
  module-level worker functions and an initializer.

Load `references/parallelization-playbook.md` for the invariants and strategies; the
template in `assets/parallel_solution.py` is a known-good implementation to diff against.

Re-run the verifier from the skill folder until `verdict` is `pass` (or the only failure is a
hardware cap you can name):
`echo '<json with "state": workspace_dir, solution_path, num_workers, num_docs, num_queries>' | python scripts/verify_solution.py`

Answer with `fix_summary` (root cause, change made) and `final_verdict` (`pass` or `fail`
from the last verifier run).
