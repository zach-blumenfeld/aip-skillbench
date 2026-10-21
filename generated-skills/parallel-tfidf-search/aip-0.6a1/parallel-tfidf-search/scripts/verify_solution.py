#!/usr/bin/env python3
"""
Verify parallel_solution.py against the sequential baseline: API shape,
exact equality of the index and of search results, and speedup with
num_workers workers (targets: index >= 1.5x, search >= 2.0x).

stdin : {"state": {workspace_dir, solution_path, num_workers, num_docs, num_queries}, ...}
stdout: {"verdict": "pass"|"fail", "failures": [...], "verification_report": {...}}

Also usable by hand after a fix:
  echo '{"state": {...}}' | python verify_solution.py
"""

import contextlib
import importlib.util
import inspect
import json
import os
import random
import sys
import time
import traceback

INDEX_TARGET = 1.5
SEARCH_TARGET = 2.0
INDEX_FIELDS = ["num_documents", "vocabulary", "document_frequencies", "idf", "inverted_index", "doc_vectors", "doc_norms"]


def load_modules(workspace, solution_path):
    sys.path.insert(0, os.path.abspath(workspace))
    import document_generator
    import sequential

    spec = importlib.util.spec_from_file_location("parallel_solution", solution_path)
    sol = importlib.util.module_from_spec(spec)
    sys.modules["parallel_solution"] = sol  # workers unpickle functions by module name
    spec.loader.exec_module(sol)
    return document_generator, sequential, sol


def make_queries(documents, n, seed):
    """Realistic mixed queries: short and long keyword queries, titles, passages, no-hit edge cases."""
    rng = random.Random(seed)
    pool = []
    for d in documents[:500]:
        pool.extend(w.strip(".,").lower() for w in d.content.split()[:60])
    pool = [w for w in pool if w.isalpha()] or ["data"]
    queries = ["", "the and of", "zzzzqx unknownterm", "machine learning algorithm", "data data data model"]
    while len(queries) < n:
        r = rng.random()
        if r < 0.15:  # a title
            queries.append(rng.choice(documents).title)
        elif r < 0.25:  # a long passage taken from a document
            words = rng.choice(documents).content.split()
            start = rng.randrange(max(1, len(words) - 30))
            queries.append(" ".join(words[start : start + rng.randint(10, 30)]))
        elif r < 0.32:  # long keyword query with repeated terms
            queries.append(" ".join(rng.choice(pool[:200]) for _ in range(rng.randint(10, 25))))
        else:  # short keyword query
            queries.append(" ".join(rng.choice(pool) for _ in range(rng.randint(1, 6))))
    return queries[:n]


def first_index_diff(a, b):
    for f in INDEX_FIELDS:
        va, vb = getattr(a, f, None), getattr(b, f, None)
        if va != vb:
            if isinstance(va, dict) and isinstance(vb, dict):
                if va.keys() != vb.keys():
                    return f"{f}: key sets differ ({len(va)} vs {len(vb)} keys)"
                for k in va:
                    if va[k] != vb[k]:
                        return f"{f}[{k!r}]: sequential {str(va[k])[:120]} != parallel {str(vb[k])[:120]}"
            return f"{f}: sequential {str(va)[:120]} != parallel {str(vb)[:120]}"
    return None


def first_search_diff(seq_results, par_results, queries, seq_mod):
    if not isinstance(par_results, list) or len(par_results) != len(seq_results):
        return f"expected a list of {len(seq_results)} result lists, got {type(par_results).__name__} of length {len(par_results) if hasattr(par_results, '__len__') else '?'}"
    for qi, (s, p) in enumerate(zip(seq_results, par_results)):
        if any(type(r) is not seq_mod.SearchResult for r in p):
            return f"query {qi}: results are not sequential.SearchResult instances (import the class from sequential, do not redefine it)"
        if s != p:
            return f"query {qi} {queries[qi]!r}: sequential {[(r.doc_id, r.score) for r in s[:3]]} != parallel {[(r.doc_id, r.score) for r in p[:3]]}"
    return None


def main():
    state = json.load(sys.stdin)["state"]
    workspace = state["workspace_dir"]
    solution_path = state["solution_path"]
    num_workers = int(state.get("num_workers", 4))
    num_docs = int(state.get("num_docs", 5000))
    num_queries = int(state.get("num_queries", 300))

    failures = []
    report = {"num_workers": num_workers, "num_docs": num_docs, "num_queries": num_queries, "cpu_count": os.cpu_count()}

    def emit():
        verdict = "pass" if not failures else "fail"
        json.dump({"verdict": verdict, "failures": failures, "verification_report": report}, sys.stdout)

    # All progress chatter (generate_corpus prints) goes to stderr; stdout is the result only.
    real_stdout = sys.stdout
    with contextlib.redirect_stdout(sys.stderr):
        try:
            dg, seq, sol = load_modules(workspace, solution_path)
        except Exception:
            failures.append("import failed: " + traceback.format_exc(limit=3))
            sys.stdout = real_stdout
            return emit()

        # ---- API shape ---------------------------------------------------
        expected = {
            "build_tfidf_index_parallel": [("documents", inspect.Parameter.empty), ("num_workers", None), ("chunk_size", 500)],
            "batch_search_parallel": [("queries", inspect.Parameter.empty), ("index", inspect.Parameter.empty), ("top_k", 10), ("num_workers", None), ("documents", None)],
        }
        for fname, params in expected.items():
            fn = getattr(sol, fname, None)
            if fn is None:
                failures.append(f"{fname} is not defined")
                continue
            sig = list(inspect.signature(fn).parameters.values())
            got = [(p.name, p.default) for p in sig[: len(params)]]
            if got != params:
                failures.append(f"{fname} signature {got} != required {params}")
        if not hasattr(sol, "ParallelIndexingResult"):
            failures.append("ParallelIndexingResult is not defined in the solution module")
        if failures:
            sys.stdout = real_stdout
            return emit()

        try:
            # ---- Correctness on small and edge-case corpora -------------
            small = dg.generate_corpus(300, seed=7)
            dup = small[:50] + [dg.Document(doc_id=small[0].doc_id, title="Dup", content="data data model", topic="x", word_count=3)]
            for label, docs, kwargs in [
                ("small corpus, 4 workers, chunk_size=37", small, {"num_workers": num_workers, "chunk_size": 37}),
                ("small corpus, default workers/chunk", small, {}),
                ("tiny corpus, more workers than docs", small[:3], {"num_workers": num_workers, "chunk_size": 1}),
                ("one worker", small[:80], {"num_workers": 1}),
                ("duplicate doc_id", dup, {"num_workers": 2, "chunk_size": 10}),
            ]:
                ref = seq.build_tfidf_index_sequential(docs).index
                res = sol.build_tfidf_index_parallel(docs, **kwargs)
                if not isinstance(res, sol.ParallelIndexingResult) or not hasattr(res, "index") or not hasattr(res, "elapsed_time"):
                    failures.append(f"[{label}] build_tfidf_index_parallel must return ParallelIndexingResult with .index and .elapsed_time")
                    continue
                if type(res.index) is not seq.TFIDFIndex:
                    failures.append(f"[{label}] index is not sequential.TFIDFIndex")
                diff = first_index_diff(ref, res.index)
                if diff:
                    failures.append(f"[{label}] index differs: {diff}")
                if res.num_documents != len(docs) or res.vocabulary_size != len(ref.vocabulary):
                    failures.append(f"[{label}] num_documents/vocabulary_size wrong")

            small_idx = seq.build_tfidf_index_sequential(small).index
            sq = make_queries(small, 60, seed=3)
            for label, kwargs, docs_arg in [
                ("search with titles", {"num_workers": num_workers}, small),
                ("search without documents", {"num_workers": num_workers}, None),
                ("search top_k=3, default workers", {"top_k": 3}, small),
                ("search one worker", {"num_workers": 1}, small),
            ]:
                k = kwargs.get("top_k", 10)
                ref = seq.batch_search_sequential(sq, small_idx, k, docs_arg)
                out = sol.batch_search_parallel(sq, small_idx, documents=docs_arg, **kwargs)
                if not (isinstance(out, tuple) and len(out) == 2 and isinstance(out[1], float)):
                    failures.append(f"[{label}] batch_search_parallel must return (results, elapsed_time)")
                    continue
                diff = first_search_diff(ref, out[0], sq, seq)
                if diff:
                    failures.append(f"[{label}] {diff}")
            empty = sol.batch_search_parallel([], small_idx, num_workers=num_workers)
            if not (isinstance(empty, tuple) and empty[0] == []):
                failures.append("empty query list must return ([], elapsed)")

            # ---- Benchmark on the full-size corpus ----------------------
            docs = dg.generate_corpus(num_docs, seed=42)
            report["total_words"] = sum(d.word_count for d in docs)

            t0 = time.perf_counter()
            seq_res = seq.build_tfidf_index_sequential(docs)
            seq_index_t = time.perf_counter() - t0
            t0 = time.perf_counter()
            par_res = sol.build_tfidf_index_parallel(docs, num_workers=num_workers)
            par_index_t = time.perf_counter() - t0
            diff = first_index_diff(seq_res.index, par_res.index)
            if diff:
                failures.append(f"[benchmark corpus] index differs: {diff}")

            queries = make_queries(docs, num_queries, seed=11)
            t0 = time.perf_counter()
            seq_out = seq.batch_search_sequential(queries, seq_res.index, 10, docs)
            seq_search_t = time.perf_counter() - t0
            t0 = time.perf_counter()
            par_out, reported = sol.batch_search_parallel(queries, seq_res.index, 10, num_workers, docs)
            par_search_t = time.perf_counter() - t0
            diff = first_search_diff(seq_out, par_out, queries, seq)
            if diff:
                failures.append(f"[benchmark corpus] {diff}")

            index_speedup = seq_index_t / par_index_t
            search_speedup = seq_search_t / par_search_t
            report.update(
                {
                    "sequential_index_s": round(seq_index_t, 3),
                    "parallel_index_s": round(par_index_t, 3),
                    "index_speedup": round(index_speedup, 2),
                    "sequential_search_s": round(seq_search_t, 3),
                    "parallel_search_s": round(par_search_t, 3),
                    "parallel_search_reported_s": round(reported, 3),
                    "search_speedup": round(search_speedup, 2),
                    "index_target": INDEX_TARGET,
                    "search_target": SEARCH_TARGET,
                }
            )
            if index_speedup < INDEX_TARGET:
                failures.append(f"index speedup {index_speedup:.2f}x < {INDEX_TARGET}x with {num_workers} workers")
            if search_speedup < SEARCH_TARGET:
                failures.append(f"search speedup {search_speedup:.2f}x < {SEARCH_TARGET}x with {num_workers} workers")
            if (os.cpu_count() or 1) < num_workers:
                report["note"] = f"only {os.cpu_count()} CPUs for {num_workers} workers; speedup is capped by hardware"
        except Exception:
            failures.append("exception during verification: " + traceback.format_exc(limit=4))

    emit()


if __name__ == "__main__":
    main()
