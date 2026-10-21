#!/usr/bin/env python3
"""
Parallel TF-IDF indexing and batch search: drop-in companion to sequential.py.

Requires: Python >= 3.9, standard library only (gc, multiprocessing, math, os, pickle,
sys, time, dataclasses). Must live in the same directory as sequential.py (and its
document_generator.py); it reuses the baseline's own tokenize(),
compute_term_frequencies(), TFIDFIndex, SearchResult, IndexingResult and
search_sequential() so results are bit-identical to the baseline.

Public API:
    build_tfidf_index_parallel(documents, num_workers=None, chunk_size=500)
        -> ParallelIndexingResult (index is a sequential.TFIDFIndex)
    batch_search_parallel(queries, index, top_k=10, num_workers=None, documents=None)
        -> (List[List[SearchResult]], elapsed_time)

Why it is fast:
  * Index: tokenize + term-frequency (the dominant per-document cost) runs in worker
    processes over many small, ordered chunks (dynamic scheduling absorbs the
    log-normal document-length skew). The baseline's O(V x D) document-frequency and
    posting-list loops are replaced by one O(total postings) pass that yields the
    same values in the same order.
  * Search: queries are independent; each worker runs the baseline's own
    search_sequential() so float summation order and top-k tie order are unchanged.
    On Linux the index is inherited through fork (copy-on-write, no pickling).

Env override (testing only): PARALLEL_TFIDF_START_METHOD=fork|spawn|forkserver.
"""

import gc
import math
import multiprocessing as mp
import os
import pickle
import sys
import time
from dataclasses import dataclass
from operator import itemgetter

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)  # spawn workers and test harnesses must find sequential.py

from sequential import (  # noqa: E402
    IndexingResult,
    SearchResult,
    TFIDFIndex,
    compute_term_frequencies,
    search_sequential,
    tokenize,
)

__all__ = [
    "ParallelIndexingResult",
    "SearchResult",
    "TFIDFIndex",
    "batch_search_parallel",
    "build_tfidf_index_parallel",
]

# Below these sizes process start-up costs more than it saves; the in-process path
# produces identical results.
MIN_DOCS_FOR_POOL = 64
MIN_QUERIES_FOR_POOL = 4
MIN_SEARCH_WORK_FOR_POOL = 50_000  # queries x indexed docs; below ~0.1 s of searching, stay in-process
# Target number of chunks per worker so fast workers pick up slack from slow ones.
CHUNKS_PER_WORKER = 4


@dataclass
class ParallelIndexingResult(IndexingResult):
    """IndexingResult (index, elapsed_time, num_documents, vocabulary_size) plus run info."""

    num_workers: int = 1
    chunk_size: int = 500
    num_chunks: int = 0


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _resolve_workers(num_workers):
    if num_workers is None:
        try:
            num_workers = len(os.sched_getaffinity(0))  # respects container CPU pinning
        except (AttributeError, OSError):
            num_workers = os.cpu_count() or 1
    return max(1, int(num_workers))


def _mp_context():
    method = os.environ.get("PARALLEL_TFIDF_START_METHOD")
    if not method:
        # fork shares the parent's memory copy-on-write (no pickling of the index).
        # It is the safe default on Linux; macOS/Windows use their platform default.
        method = "fork" if sys.platform.startswith("linux") else None
    return mp.get_context(method)


def _chunks(seq, size):
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def _freeze_inherited_heap():
    """Worker initializer: move every inherited object out of the cyclic GC's reach.

    The parent's heap (corpus, index, caller's data) can be millions of objects; without
    this each full collection in a worker re-scans all of it (and dirties copy-on-write
    pages). Results are unaffected: gc only reclaims cycles, which this code never makes.
    """
    gc.freeze()


class _GcPaused:
    """Pause the cyclic GC around allocation-heavy single-threaded phases (restores prior state)."""

    def __enter__(self):
        self._was_enabled = gc.isenabled()
        gc.disable()

    def __exit__(self, *exc):
        if self._was_enabled:
            gc.enable()


# ----------------------------------------------------------------------------
# Index building
# ----------------------------------------------------------------------------


def _tf_chunk(chunk):
    """Worker: (doc_id, title, content) triples -> [(doc_id, tf_dict)] in input order."""
    return [(doc_id, compute_term_frequencies(tokenize(title + " " + content))) for doc_id, title, content in chunk]


def _assemble_index(num_documents, tf_pairs):
    """Single-pass equivalent of baseline steps 1(merge)-5; identical values and order."""
    index = TFIDFIndex()
    index.num_documents = num_documents

    doc_term_freqs = {}
    vocabulary = index.vocabulary
    for doc_id, tf in tf_pairs:  # document order; duplicate doc_ids: last wins, like the baseline
        doc_term_freqs[doc_id] = tf
        vocabulary.update(tf.keys())

    df_counts = {}
    for tf in doc_term_freqs.values():
        for term in tf:
            df_counts[term] = df_counts.get(term, 0) + 1
    index.document_frequencies = {term: df_counts.get(term, 0) for term in vocabulary}

    N = index.num_documents
    idf = {term: math.log(N / df) + 1 for term, df in index.document_frequencies.items()}
    index.idf = idf

    postings = {term: [] for term in vocabulary}
    doc_vectors = index.doc_vectors
    doc_norms = index.doc_norms
    for doc_id, tf_dict in doc_term_freqs.items():  # same doc order as the baseline's per-term scan
        doc_vector = {}
        norm_squared = 0.0
        for term, tf in tf_dict.items():
            tfidf = tf * idf[term]
            doc_vector[term] = tfidf
            norm_squared += tfidf * tfidf
            postings[term].append((doc_id, tfidf))
        doc_vectors[doc_id] = doc_vector
        doc_norms[doc_id] = math.sqrt(norm_squared)

    by_score = itemgetter(1)  # same key as the baseline's lambda x: x[1], just faster
    for posting_list in postings.values():
        posting_list.sort(key=by_score, reverse=True)  # stable: ties keep doc order
    index.inverted_index = postings
    return index


def build_tfidf_index_parallel(documents, num_workers=None, chunk_size=500):
    """Build the same TFIDFIndex as build_tfidf_index_sequential, using worker processes."""
    start_time = time.perf_counter()
    documents = list(documents)
    n = len(documents)
    workers = _resolve_workers(num_workers)
    chunk_size = max(1, int(chunk_size or 500))

    payload = [(d.doc_id, d.title, d.content) for d in documents]
    # Shrink chunks so every worker gets several (dynamic load balancing over skewed lengths).
    effective_chunk = max(1, min(chunk_size, math.ceil(n / (workers * CHUNKS_PER_WORKER)) if n else 1))
    chunks = _chunks(payload, effective_chunk)

    # Unpickling worker results and assembling allocate millions of objects; with a big
    # caller heap each automatic full GC pass would re-scan it all. Pause GC meanwhile.
    with _GcPaused():
        if workers == 1 or n < MIN_DOCS_FOR_POOL or len(chunks) < 2:
            tf_pairs = _tf_chunk(payload)
            used_workers = 1
        else:
            used_workers = min(workers, len(chunks))
            with _mp_context().Pool(processes=used_workers, initializer=_freeze_inherited_heap) as pool:
                tf_pairs = [pair for part in pool.imap(_tf_chunk, chunks) for pair in part]
        index = _assemble_index(n, tf_pairs)
    elapsed = time.perf_counter() - start_time
    return ParallelIndexingResult(
        index=index,
        elapsed_time=elapsed,
        num_documents=n,
        vocabulary_size=len(index.vocabulary),
        num_workers=used_workers,
        chunk_size=effective_chunk,
        num_chunks=len(chunks),
    )


# ----------------------------------------------------------------------------
# Batch search
# ----------------------------------------------------------------------------

_SEARCH_STATE = None  # (index, top_k, documents) visible to workers


def _init_search(state_bytes=None):
    global _SEARCH_STATE
    if state_bytes is not None:
        _SEARCH_STATE = pickle.loads(state_bytes)
    _freeze_inherited_heap()


def _search_chunk(queries):
    index, top_k, documents = _SEARCH_STATE
    return [search_sequential(q, index, top_k, documents) for q in queries]


def batch_search_parallel(queries, index, top_k=10, num_workers=None, documents=None):
    """Search many queries in parallel. Returns (results_per_query, elapsed_seconds)."""
    global _SEARCH_STATE
    start_time = time.perf_counter()
    queries = list(queries)
    workers = min(_resolve_workers(num_workers), max(1, len(queries)))

    work = len(queries) * len(getattr(index, "doc_norms", ()) or ())
    if workers == 1 or len(queries) < MIN_QUERIES_FOR_POOL or work < MIN_SEARCH_WORK_FOR_POOL:
        results = [search_sequential(q, index, top_k, documents) for q in queries]
        return results, time.perf_counter() - start_time

    size = max(1, math.ceil(len(queries) / (workers * CHUNKS_PER_WORKER)))
    chunks = _chunks(queries, size)
    ctx = _mp_context()
    previous = _SEARCH_STATE
    try:
        if ctx.get_start_method() == "fork":
            _SEARCH_STATE = (index, top_k, documents)  # inherited copy-on-write, nothing pickled
            pool = ctx.Pool(processes=workers, initializer=_init_search)
        else:
            # spawn/forkserver: pickle the index ONCE; each worker unpickles it in parallel.
            # (Passing the objects as initargs would re-pickle them serially per worker.)
            state = pickle.dumps((index, top_k, documents), protocol=pickle.HIGHEST_PROTOCOL)
            pool = ctx.Pool(processes=workers, initializer=_init_search, initargs=(state,))
        with pool, _GcPaused():
            results = [res for part in pool.imap(_search_chunk, chunks) for res in part]
    finally:
        _SEARCH_STATE = previous
    return results, time.perf_counter() - start_time


if __name__ == "__main__":
    import argparse

    from document_generator import generate_corpus, load_corpus

    parser = argparse.ArgumentParser(description="Parallel TF-IDF indexing and search demo")
    parser.add_argument("--corpus", default=None, help="Corpus JSON (save_corpus format)")
    parser.add_argument("--num-docs", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--query", default="machine learning algorithm")
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()

    docs = load_corpus(args.corpus) if args.corpus else generate_corpus(args.num_docs, seed=42)
    res = build_tfidf_index_parallel(docs, num_workers=args.workers)
    print(f"Indexed {res.num_documents} docs, vocab {res.vocabulary_size}, {res.elapsed_time:.3f}s, workers={res.num_workers}")
    out, t = batch_search_parallel([args.query], res.index, args.top_k, args.workers, docs)
    for i, r in enumerate(out[0], 1):
        print(f"  {i}. [{r.score:.4f}] {r.title} (doc_id: {r.doc_id})")
