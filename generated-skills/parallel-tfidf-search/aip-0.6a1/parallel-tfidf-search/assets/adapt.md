# Adapt the parallel TF-IDF solution

The baseline in `{workspace_dir}` differs from what the bundled template assumes:

{deviations}

Baseline profile (Python, CPUs, start methods, semantics found): {baseline_profile}

Write `{solution_path}` so that it provides
`build_tfidf_index_parallel(documents, num_workers=None, chunk_size=500)` returning a
`ParallelIndexingResult` (with `.index` of the baseline's own `TFIDFIndex` class,
`.elapsed_time`, `.num_documents`, `.vocabulary_size`) and
`batch_search_parallel(queries, index, top_k=10, num_workers=None, documents=None)`
returning `(List[List[SearchResult]], elapsed_time)`, with results identical (`==`) to the
baseline and >= 1.5x index / >= 2x search speedup at 4 workers.

How:
1. Read the baseline `sequential.py` (and any module it imports) in full. List every
   formula, ordering and tie rule it uses; the deviations above say which ones differ.
2. Start from the template below. Keep its structure: data published in a module global
   before a fork-context pool, ordered `imap` over contiguous chunks, merge in document
   order, baseline classes and helpers imported rather than redefined, search scored per query
   in workers. If the baseline's search formula differs, replace `_score_query` with a call to
   the baseline's own per-query search function (identical by construction) rather than
   re-deriving the fast path.
3. Change only what the deviations require: renamed functions/fields, a different IDF or TF
   formula, different text fields, different sort or tie rule. Mirror the baseline's
   arithmetic expression and iteration order exactly so floats match bit for bit.
4. Use only the standard library (the container is python:3.12-slim, no numpy).
5. Run the verifier the next step also runs, and fix until `verdict` is `pass`:
   `echo '<json with "state": workspace_dir, solution_path, num_workers, num_docs, num_queries>' | python scripts/verify_solution.py`
   (from the skill folder; the verifier expects the API names above, so if the task
   statement names different functions, state that in your notes).

Load `references/parallelization-playbook.md` for the exactness invariants, strategy,
balancing and memory rules before editing.

Template (`assets/parallel_solution.py`):

{assets[parallel_solution]}

Answer with `adaptation_notes`: what you changed relative to the template and why, and the
verifier result you got.
