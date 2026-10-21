---
name: parallel-tfidf-search
description: Parallelize a sequential Python TF-IDF search engine (inverted index build + cosine-similarity batch search) with multiprocessing so it runs faster on multi-core machines while producing bit-identical results. Use when asked to write parallel_solution.py with build_tfidf_index_parallel / batch_search_parallel, to speed up TF-IDF indexing or document similarity search across cores, or to hit a speedup target (e.g. 1.5x index, 2x search at 4 workers) against a sequential baseline. Covers process-pool strategy, fork vs spawn, copy-on-write sharing of large read-only data, chunked dynamic load balancing for long-tailed document lengths, memory-lean worker returns, exact float/tie-order equivalence, and a verifier for correctness and speedup.
metadata:
  aip-version: "0.6a1"
---

# AIP runtime — format 0.6a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the one JSON object a run carries. Each step declares the keys it reads as `inputs`; `execution` and `client_task` steps declare the keys they add as `outputs`, and a `decision` adds one key per question.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the procedure's result.

## Execution

The state starts as the start step's `inputs` and flows along `inputs_to`; each step adds its outputs to it. Every key is produced by exactly one step, so keys accumulate and nothing is overwritten. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. A step sees only those keys: give it its declared `inputs` and nothing else from the state. You have the final say at every step.

- **`execution`**: before the first one, check that this machine has everything `requires` names (the interpreter at its minimum version, the packages, the tools); if anything is missing, stop and name all of it. Run `script` from its folder, launched with the step's `command` when it has one and `python <script>` otherwise, with one JSON object on stdin, `{"state": <the step's inputs>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout holding exactly the step's `outputs`; add them to the state. A non-zero exit, or output missing a declared key, fails the step: stop there and report it rather than doing the step by hand.
- **`decision`**: answer each question from the step's inputs, and from the run so far only when the step sets `history: true`. Each answer collapses to one value under its question name and is added to the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the step's inputs, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the step's `outputs`; add them to the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. Those keys are the procedure's result.

```yaml
purpose: >
  Turn a single-threaded TF-IDF search engine (sequential.py: tokenize, term frequencies,
  inverted index, cosine-similarity search) into parallel_solution.py exposing
  build_tfidf_index_parallel(documents, num_workers=None, chunk_size=500) -> ParallelIndexingResult
  and batch_search_parallel(queries, index, top_k=10, num_workers=None, documents=None)
  -> (List[List[SearchResult]], elapsed_time), with results identical (==) to the baseline and
  at least 1.5x index / 2x search speedup at 4 workers. A script checks the baseline against the
  bundled, tested template; the template is installed as-is or adapted; a verifier then checks API,
  exact equality and speedup on a generated corpus, and a fix task handles any failure.

trigger_when:
  - A task asks to parallelize a sequential TF-IDF indexer or similarity search engine in Python.
  - A task asks for parallel_solution.py with build_tfidf_index_parallel and batch_search_parallel.
  - A sequential CPU-bound Python workload over documents must use all cores while keeping identical output.
  - A speedup target over a sequential Python baseline must be met with a fixed number of workers.

do_not_use_when:
  - The workload is I/O-bound (network, disk, database); use asyncio or threads instead.
  - The search engine is not TF-IDF/cosine based or is not Python (e.g. a vector database, Elasticsearch).
  - Approximate results are acceptable and the goal is a different ranking model.

requires:
  interpreter:
    name: python
    version: "3.10"

steps:
  - name: inspect
    kind: execution
    description: >
      Parse the workspace's sequential.py and document_generator.py; check every class, field,
      function and parameter the template imports, and the formulas it reproduces: index (title + " " +
      content text, IDF = log(N/df) + 1, TF-IDF = tf * idf, stable score-descending posting sort,
      whole posting lists, sqrt norm, N = len(documents)) and search (unmodified query tokens,
      known-term query weights, candidate set, builtin-sum dot product, zero-norm skip, cosine,
      nlargest, default titles). Report CPU count and multiprocessing start methods. Plan is
      "template" when nothing deviates, "adapt" otherwise.
    inputs:
      - name: workspace_dir
        type: string
        description: Folder holding sequential.py and document_generator.py (in the task container, /root/workspace).
      - name: solution_path
        type: string
        description: Where the solution must be written (in the task container, /root/workspace/parallel_solution.py). Must be inside workspace_dir.
      - name: num_workers
        type: integer
        description: Worker count the speedup target is stated for (4 unless the task says otherwise).
      - name: num_docs
        type: integer
        description: Size of the generated benchmark corpus for verification (5000 matches the baseline's default).
      - name: num_queries
        type: integer
        description: Number of benchmark queries for verification (300 is enough for a stable search timing).
    script: scripts/inspect_baseline.py
    outputs:
      - name: plan
        type: string
        description: '"template" if the baseline matches the template''s assumptions, else "adapt".'
      - name: deviations
        type: list[*]
        description: Each mismatch between the baseline and the template's assumptions; empty for "template".
      - name: baseline_profile
        type: object
        description: Workspace files, whether a solution already exists, Python version, cpu_count, start methods, semantics matched.
    inputs_to: by-plan

  - name: by-plan
    kind: router
    description: Install the tested template when the baseline matches it; otherwise adapt it to the baseline.
    branch_on: plan
    branches:
      template: install
      adapt: adapt

  - name: install
    kind: execution
    description: >
      Write the bundled assets/parallel_solution.py to solution_path (a differing existing file is
      kept as .bak). The template imports the baseline's own classes and helpers, publishes documents
      or the index in a module global before a fork-context pool (spawn falls back to an initializer),
      maps tokenize + TF over contiguous chunk_size chunks with ordered imap, merges in document order
      in one pass (DF, IDF, posting lists, vectors, norms), and scores queries in workers (about 4
      chunks per worker) from the posting lists with the baseline's exact float expressions, builtin
      sum and candidate order, attaching titles once in the parent.
    inputs:
      - name: workspace_dir
        type: string
      - name: solution_path
        type: string
    script: scripts/install_template.py
    assets:
      - assets/parallel_solution.py
    outputs:
      - name: installed_path
        type: string
        description: Absolute path of the written solution.
      - name: installed_bytes
        type: integer
        description: Size of the written solution in bytes.
    inputs_to: verify

  - name: adapt
    kind: client_task
    description: Write solution_path by adapting the template to the baseline's deviations while keeping every exactness invariant.
    inputs:
      - name: workspace_dir
        type: string
      - name: solution_path
        type: string
      - name: deviations
        type: list[*]
      - name: baseline_profile
        type: object
    template: assets/adapt.md
    assets:
      - assets/parallel_solution.py
    references:
      - path: references/parallelization-playbook.md
        description: Exactness invariants, time profile, strategy decision tree, start methods, balancing and memory rules, verification checklist. Load before editing the solution.
      - path: references/python-parallelization-advanced.md
        description: Shared memory, chunked executors, error-handling patterns. Only if the baseline needs a pattern the template does not use.
      - path: references/workload-balancing-advanced.md
        description: Adaptive batch sizing, priority and locality-aware scheduling, MapReduce shuffling. Only if load is still uneven after dynamic chunking.
      - path: references/memory-optimization-advanced.md
        description: Copy-on-write, flyweight, weak caches, streaming JSON. Only if worker memory or result transfer becomes the bottleneck.
    outputs:
      - name: adaptation_notes
        type: string
        description: What changed relative to the template and why, plus the verifier result obtained.
    inputs_to: verify

  - name: verify
    kind: execution
    description: >
      Import the solution next to the baseline; check both signatures and defaults, the return types
      (ParallelIndexingResult with the baseline's TFIDFIndex; (results, float) with sequential.SearchResult),
      exact equality of all seven index fields and of search results on small, default-argument,
      tiny (more workers than docs), one-worker, duplicate-doc_id, no-documents, top_k and empty-query
      cases, with short, long (10-30 word), repeated-term, title and no-hit queries; then time sequential vs parallel on a num_docs corpus and num_queries queries with
      num_workers workers against the 1.5x index and 2.0x search targets.
    inputs:
      - name: workspace_dir
        type: string
      - name: solution_path
        type: string
      - name: num_workers
        type: integer
      - name: num_docs
        type: integer
      - name: num_queries
        type: integer
    script: scripts/verify_solution.py
    timeout: 1800
    outputs:
      - name: verdict
        type: string
        description: '"pass" when every correctness check and both speedup targets hold, else "fail".'
      - name: failures
        type: list[*]
        description: One line per failed check, with the first differing field or query.
      - name: verification_report
        type: object
        description: cpu_count, corpus size, sequential and parallel timings, index_speedup, search_speedup, targets.
    inputs_to: by-verdict

  - name: by-verdict
    kind: router
    description: Finish on a pass; diagnose and fix on any failure.
    branch_on: verdict
    branches:
      pass: end
      fail: fix

  - name: fix
    kind: client_task
    description: Diagnose each failure by type, edit the solution, and re-run the verifier until it passes or the only remaining failure is a named hardware cap.
    inputs:
      - name: workspace_dir
        type: string
      - name: solution_path
        type: string
      - name: failures
        type: list[*]
      - name: verification_report
        type: object
    template: assets/fix.md
    references:
      - path: references/parallelization-playbook.md
        description: Exactness invariants and the speedup levers. Load for any correctness or speed failure.
      - path: references/python-parallelization-advanced.md
        description: Error-handling and shared-memory patterns. Only for exceptions in workers or data-transfer bottlenecks.
    outputs:
      - name: fix_summary
        type: string
        description: Root cause of each failure and the change made.
      - name: final_verdict
        type: string
        description: '"pass" or "fail" from the last verifier run after the fix.'
    inputs_to: end

  - name: end
    kind: end
    description: The written solution and the verifier's verdict and measurements (on the fix path, fix_summary and final_verdict record the re-verification).
    inputs:
      - name: solution_path
        type: string
      - name: verdict
        type: string
      - name: verification_report
        type: object

anti_patterns:
  - Redefining TFIDFIndex, SearchResult or IndexingResult in the solution; dataclass equality fails across classes, so results never compare equal. Import them from sequential.
  - Re-implementing tokenize or the TF formula instead of importing them, or changing a search expression; any difference in regex, float expression or summation order breaks bit-identical results.
  - Accumulating dot products with acc += x; Python 3.12+ sum() is compensated, so collect the products and call builtin sum() as the baseline does.
  - Merging worker results with imap_unordered or as_completed; posting-list ties and dict order must follow the original document order.
  - Using threads for the CPU-bound work; the GIL serializes it and the speedup stays near 1x.
  - Passing the index or the document list as a per-task argument; every task pickles a full copy. Publish it in a module global before forking (or send it once via an initializer under spawn).
  - Lambdas, nested functions or bound methods as worker functions; they cannot be pickled. Keep worker functions at module level.
  - Re-scanning vocabulary x documents for DF and postings as the baseline does; one pass over the TF dicts gives the same result.
  - Importing numpy, pandas or other third-party packages; the container (python:3.12-slim) has only the standard library.
  - Hardcoding results, timings or corpus contents; compute everything from the documents and queries passed in.
  - Reporting a pass when the machine has fewer CPUs than num_workers and the speedup target was missed; report the hardware cap instead.
```
