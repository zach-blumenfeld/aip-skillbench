#!/usr/bin/env python3
"""
Verify a parallel Python rewrite against its sequential baseline.

Tailored for the curated parallel-TF-IDF benchmark interface:
  sequential.build_tfidf_index_sequential(documents) -> IndexingResult
  sequential.batch_search_sequential(queries, index, top_k, documents) -> list[list[SearchResult]]
  <parallel_module>.build_tfidf_index_parallel(documents, num_workers, chunk_size) -> ParallelIndexingResult
  <parallel_module>.batch_search_parallel(queries, index, top_k, num_workers, documents) -> (list[list[SearchResult]], elapsed)

Runs three checks:
  1. Correctness — IDF values and top-k search results agree with the
     sequential baseline within tolerance.
  2. Index-build speedup — wall-clock ratio (sequential / parallel) meets target.
  3. Batch-search speedup — wall-clock ratio meets target.

Exit code is 0 on full pass, 1 on any failure. JSON-Lines diagnostics go to
stderr; a human summary goes to stdout. Designed for the agent to run after
writing parallel_solution.py and iterate on red findings.

Usage:
  python verify_parallel.py \
      --workspace /root/workspace \
      --parallel-module parallel_solution \
      --num-workers 4 \
      --index-speedup 1.5 \
      --search-speedup 2.0 \
      --small-corpus 1000 \
      --perf-corpus 5000 \
      --num-queries 1000
"""

from __future__ import annotations

import argparse
import importlib
import json
import random
import sys
import time
from pathlib import Path


def _jsonl(stream, level: str, check: str, **fields) -> None:
    rec = {"level": level, "check": check, **fields}
    stream.write(json.dumps(rec, default=str) + "\n")
    stream.flush()


def _import_workspace(workspace: Path, parallel_module: str):
    sys.path.insert(0, str(workspace))
    try:
        seq = importlib.import_module("sequential")
        docgen = importlib.import_module("document_generator")
        par = importlib.import_module(parallel_module)
    except ImportError as e:
        _jsonl(sys.stderr, "error", "import", message=str(e))
        raise SystemExit(1)
    for name in ("build_tfidf_index_parallel", "batch_search_parallel"):
        if not hasattr(par, name):
            _jsonl(sys.stderr, "error", "interface", missing=name, module=parallel_module)
            raise SystemExit(1)
    return seq, docgen, par


def _generate_queries(n: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    base = [
        "machine", "learning", "algorithm", "neural", "network",
        "database", "optimization", "performance", "clinical", "trial",
        "market", "analysis", "investment", "research", "methodology",
    ]
    return [" ".join(rng.choices(base, k=rng.randint(1, 20))) for _ in range(n)]


def _check_idf(seq_index, par_index, tol: float) -> bool:
    diffs = 0
    for term in seq_index.vocabulary:
        if abs(seq_index.idf.get(term, 0) - par_index.idf.get(term, 0)) > tol:
            diffs += 1
    if diffs:
        _jsonl(sys.stderr, "error", "idf", terms_differing=diffs, tolerance=tol)
        return False
    return True


def _check_search_equiv(seq_results, par_results, tol: float) -> bool:
    if len(seq_results) != len(par_results):
        _jsonl(sys.stderr, "error", "search.count", seq=len(seq_results), par=len(par_results))
        return False
    for i, (s, p) in enumerate(zip(seq_results, par_results)):
        if len(s) != len(p):
            _jsonl(sys.stderr, "error", "search.result_len", query_idx=i, seq=len(s), par=len(p))
            return False
        for j, (a, b) in enumerate(zip(s, p)):
            if a.doc_id != b.doc_id:
                _jsonl(sys.stderr, "error", "search.doc_id", query_idx=i, rank=j, seq=a.doc_id, par=b.doc_id)
                return False
            if abs(a.score - b.score) > tol:
                _jsonl(sys.stderr, "error", "search.score", query_idx=i, rank=j, seq=a.score, par=b.score)
                return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="/root/workspace", type=Path)
    ap.add_argument("--parallel-module", default="parallel_solution")
    ap.add_argument("--num-workers", type=int, default=4)
    ap.add_argument("--index-speedup", type=float, default=1.5)
    ap.add_argument("--search-speedup", type=float, default=2.0)
    ap.add_argument("--small-corpus", type=int, default=1000)
    ap.add_argument("--perf-corpus", type=int, default=5000)
    ap.add_argument("--num-queries", type=int, default=1000)
    ap.add_argument("--tolerance", type=float, default=1e-6)
    ap.add_argument("--corpus-seed", type=int, default=42)
    ap.add_argument("--perf-seed", type=int, default=789)
    ap.add_argument("--query-seed", type=int, default=202)
    args = ap.parse_args()

    seq_mod, docgen, par_mod = _import_workspace(args.workspace, args.parallel_module)

    failures: list[str] = []

    # ---- 1. Correctness on a small corpus ----------------------------------
    small = docgen.generate_corpus(args.small_corpus, seed=args.corpus_seed)
    seq_idx = seq_mod.build_tfidf_index_sequential(small).index
    par_idx = par_mod.build_tfidf_index_parallel(
        small, num_workers=args.num_workers
    ).index

    if not _check_idf(seq_idx, par_idx, args.tolerance):
        failures.append("idf-mismatch")

    sample_queries = [
        "machine learning algorithm",
        "database optimization",
        "clinical trial treatment",
    ]
    seq_search = seq_mod.batch_search_sequential(sample_queries, seq_idx, top_k=10, documents=small)
    par_search, _ = par_mod.batch_search_parallel(
        sample_queries, par_idx, top_k=10, num_workers=args.num_workers, documents=small
    )
    if not _check_search_equiv(seq_search, par_search, args.tolerance):
        failures.append("search-mismatch")

    # ---- 2. Index-build speedup -------------------------------------------
    perf = docgen.generate_corpus(args.perf_corpus, seed=args.perf_seed)

    t0 = time.perf_counter()
    seq_mod.build_tfidf_index_sequential(perf)
    seq_index_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    par_mod.build_tfidf_index_parallel(perf, num_workers=args.num_workers)
    par_index_time = time.perf_counter() - t0

    index_speedup = seq_index_time / par_index_time if par_index_time > 0 else float("inf")
    if index_speedup < args.index_speedup:
        _jsonl(sys.stderr, "error", "perf.index", seq=seq_index_time, par=par_index_time,
               speedup=index_speedup, target=args.index_speedup)
        failures.append("index-speedup")

    # ---- 3. Batch-search speedup ------------------------------------------
    perf_index = par_mod.build_tfidf_index_parallel(perf, num_workers=args.num_workers).index
    queries = _generate_queries(args.num_queries, seed=args.query_seed)

    t0 = time.perf_counter()
    seq_mod.batch_search_sequential(queries, perf_index, top_k=10, documents=perf)
    seq_search_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    par_mod.batch_search_parallel(queries, perf_index, top_k=10,
                                  num_workers=args.num_workers, documents=perf)
    par_search_time = time.perf_counter() - t0

    search_speedup = seq_search_time / par_search_time if par_search_time > 0 else float("inf")
    if search_speedup < args.search_speedup:
        _jsonl(sys.stderr, "error", "perf.search", seq=seq_search_time, par=par_search_time,
               speedup=search_speedup, target=args.search_speedup)
        failures.append("search-speedup")

    # ---- Summary -----------------------------------------------------------
    print(
        f"correctness=idf:{ 'ok' if 'idf-mismatch' not in failures else 'FAIL' } "
        f"search:{ 'ok' if 'search-mismatch' not in failures else 'FAIL' } "
        f"index_speedup={index_speedup:.2f}x (target {args.index_speedup}x) "
        f"search_speedup={search_speedup:.2f}x (target {args.search_speedup}x)"
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
