#!/usr/bin/env python3
"""
Parallel TF-IDF Implementation

Parallel drop-in for sequential.py:
1. build_tfidf_index_parallel  -> ParallelIndexingResult (same TFIDFIndex structure)
2. batch_search_parallel       -> (List[List[SearchResult]], elapsed_time)

Results are identical to the sequential baseline:
- tokenize / compute_term_frequencies are imported from sequential.py, so
  tokens, TF floats and dict insertion order are the same.
- Search scores each query from the posting lists instead of probing every
  candidate's dict once per query term, with the same floats: products are
  formed as query_weight * posting_weight (posting weights are the same
  tf * idf values as doc_vectors), summed with builtin sum() over the same
  non-zero products in query-term order (absent terms only add 0.0), and the
  candidate set is built in the same insertion order so nlargest breaks ties
  the same way.
- Documents are merged in their original order, so every dict keeps the
  baseline's insertion order, posting lists are filled in document order
  before the same stable sort, and norms sum terms in the same order.
- TFIDFIndex / SearchResult / IndexingResult are the baseline's own classes
  (dataclass __eq__ requires the same class).

Parallelism: CPU-bound Python, so processes, not threads (GIL). Large
read-only data (documents, index) is published in a module global *before*
the pool forks, so workers inherit it copy-on-write instead of receiving a
pickled copy per task. Work is handed out in contiguous chunks through
imap (ordered, dynamic): document lengths are long-tailed, so many small
chunks keep workers evenly loaded while order is preserved for the merge.
"""

import gc
import math
import multiprocessing as mp
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass
from heapq import nlargest
from operator import itemgetter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from document_generator import Document  # noqa: E402,F401
from sequential import (  # noqa: E402
    IndexingResult,
    SearchResult,
    TFIDFIndex,
    compute_term_frequencies,
    tokenize,
)

__all__ = [
    "ParallelIndexingResult",
    "SearchResult",
    "TFIDFIndex",
    "batch_search_parallel",
    "build_tfidf_index_parallel",
]


@dataclass
class ParallelIndexingResult(IndexingResult):
    """IndexingResult (index, elapsed_time, num_documents, vocabulary_size) plus worker info."""

    num_workers: int = 1
    chunk_size: int = 500


# ============================================================================
# Worker plumbing
# ============================================================================

# Read-only data shared with workers (inherited on fork, sent once via initializer otherwise).
_DOCS = None  # list of (doc_id, text)
_INDEX = None  # TFIDFIndex

# Approximate cost of starting a worker pool that inherits the index (seconds).
POOL_STARTUP_S = 0.05


def _context():
    """Prefer fork (Linux default before 3.14): workers inherit globals with no pickling."""
    if "fork" in mp.get_all_start_methods():
        return mp.get_context("fork")
    return mp.get_context()


def _set_docs(docs):
    global _DOCS
    _DOCS = docs


def _set_index(index):
    global _INDEX
    _INDEX = index


def _make_pool(num_workers, setter, payload):
    ctx = _context()
    if ctx.get_start_method() == "fork":
        setter(payload)
        gc.freeze()  # keep inherited objects out of GC scans so pages stay shared
        return ctx.Pool(processes=num_workers)
    return ctx.Pool(processes=num_workers, initializer=setter, initargs=(payload,))


def _resolve_workers(num_workers):
    if num_workers is None:
        num_workers = os.cpu_count() or 1
    return max(1, int(num_workers))


def _ranges(n, size):
    size = max(1, int(size))
    return [(i, min(i + size, n)) for i in range(0, n, size)]


# ============================================================================
# Parallel Index Building
# ============================================================================


def _tf_range(bounds):
    """Tokenize + TF for documents [start, end); also partial document frequencies."""
    start, end = bounds
    out = []
    df = Counter()
    for doc_id, text in _DOCS[start:end]:
        tf = compute_term_frequencies(tokenize(text))
        out.append((doc_id, tf))
        df.update(tf.keys())
    return out, df


def build_tfidf_index_parallel(documents, num_workers=None, chunk_size=500):
    """
    Build the TF-IDF index with a process pool.

    Map (parallel): tokenize + term frequencies per chunk of documents.
    Reduce (main):  merge in document order, document frequencies, IDF,
                    posting lists, document vectors and norms in one pass
                    over the TF dicts (the baseline scans vocabulary x docs).
    """
    start_time = time.perf_counter()
    num_workers = _resolve_workers(num_workers)
    documents = list(documents)
    n = len(documents)

    index = TFIDFIndex()
    index.num_documents = n

    docs = [(d.doc_id, d.title + " " + d.content) for d in documents]
    ranges = _ranges(n, chunk_size)

    # ---- Map: TF per document -------------------------------------------
    parts = []
    if num_workers == 1 or len(ranges) <= 1:
        _set_docs(docs)
        parts = [_tf_range(r) for r in ranges]
    else:
        pool = _make_pool(min(num_workers, len(ranges)), _set_docs, docs)
        try:
            parts = list(pool.imap(_tf_range, ranges))
        finally:
            pool.terminate()
            pool.join()
            gc.unfreeze()
    _set_docs(None)

    # ---- Merge in document order (same insertion order as the baseline) ----
    doc_term_freqs = {}
    vocabulary = index.vocabulary
    for chunk, _ in parts:
        for doc_id, tf in chunk:
            doc_term_freqs[doc_id] = tf
            vocabulary.update(tf.keys())

    # ---- Document frequencies -------------------------------------------
    if len(doc_term_freqs) == n:  # unique doc_ids: partial counts are exact
        df_total = Counter()
        for _, df in parts:
            df_total.update(df)
    else:  # duplicate doc_ids: the baseline counts each doc_id once (last TF wins)
        df_total = Counter()
        for tf in doc_term_freqs.values():
            df_total.update(tf.keys())
    del parts
    for term in vocabulary:
        index.document_frequencies[term] = df_total[term]

    # ---- IDF: log(N / DF) + 1 ------------------------------------------
    N = index.num_documents
    idf = index.idf
    for term, df in index.document_frequencies.items():
        idf[term] = math.log(N / df) + 1

    # ---- Posting lists + document vectors + norms (one pass) -------------
    postings = {term: [] for term in vocabulary}
    for doc_id, tf_dict in doc_term_freqs.items():
        doc_vector = {}
        norm_squared = 0.0
        for term, tf in tf_dict.items():
            tfidf = tf * idf[term]
            doc_vector[term] = tfidf
            norm_squared += tfidf * tfidf
            postings[term].append((doc_id, tfidf))
        index.doc_vectors[doc_id] = doc_vector
        index.doc_norms[doc_id] = math.sqrt(norm_squared)

    # Stable sort by score descending: ties keep document order, as in the baseline.
    inverted_index = index.inverted_index
    by_score = itemgetter(1)
    for term in vocabulary:
        plist = postings[term]
        plist.sort(key=by_score, reverse=True)
        inverted_index[term] = plist

    elapsed = time.perf_counter() - start_time
    return ParallelIndexingResult(
        index=index,
        elapsed_time=elapsed,
        num_documents=n,
        vocabulary_size=len(vocabulary),
        num_workers=num_workers,
        chunk_size=chunk_size,
    )


# ============================================================================
# Parallel Search
# ============================================================================


def _score_query(query, index, top_k):
    """
    Same (doc_id, score) list as sequential.search_sequential, computed from the
    posting lists. Keep every expression and iteration order below as is: they
    are what makes the floats and the tie order identical.
    """
    query_tokens = tokenize(query)
    if not query_tokens:
        return []
    query_tf = compute_term_frequencies(query_tokens)

    idf = index.idf
    query_vector = {}
    query_norm_squared = 0.0
    for term, tf in query_tf.items():
        if term in idf:
            tfidf = tf * idf[term]
            query_vector[term] = tfidf
            query_norm_squared += tfidf * tfidf
    if not query_vector:
        return []
    query_norm = math.sqrt(query_norm_squared)

    # Candidates in the baseline's insertion order; products per doc in query-term order.
    inverted_index = index.inverted_index
    candidate_docs = set()
    products = {}
    for term, q_weight in query_vector.items():
        if term in inverted_index:
            for doc_id, d_weight in inverted_index[term]:
                candidate_docs.add(doc_id)
                plist = products.get(doc_id)
                if plist is None:
                    products[doc_id] = [q_weight * d_weight]
                else:
                    plist.append(q_weight * d_weight)

    doc_norms = index.doc_norms
    scores = []
    for doc_id in candidate_docs:
        doc_norm = doc_norms.get(doc_id, 0)
        if doc_norm == 0:
            continue
        # builtin sum, like the baseline (compensated on 3.12+); missing terms only add 0.0
        scores.append((doc_id, sum(products[doc_id]) / (query_norm * doc_norm)))

    return nlargest(top_k, scores, key=itemgetter(1))


def _search_range(args):
    """Score queries [start, end) against the shared index; return (doc_id, score) pairs."""
    queries, top_k = args
    return [_score_query(q, _INDEX, top_k) for q in queries]


def batch_search_parallel(queries, index, top_k=10, num_workers=None, documents=None):
    """
    Search many queries in parallel.

    Returns (List[List[SearchResult]], elapsed_time). Queries are split into
    contiguous chunks scored in workers by _score_query (identical to the
    baseline's search_sequential); titles are attached once in the parent from
    a single lookup table instead of rebuilding it per query.

    Over-parallelization guard: a few queries are scored in-process first to
    measure the per-query cost; the pool is started only when the remaining
    work outweighs its start-up cost, otherwise the rest stays in-process.
    """
    start_time = time.perf_counter()
    num_workers = _resolve_workers(num_workers)
    queries = list(queries)
    nq = len(queries)

    raw = []  # one list of (doc_id, score) per query, in query order
    head = min(nq, 2 * num_workers) if num_workers > 1 else nq
    t0 = time.perf_counter()
    raw.extend(_score_query(q, index, top_k) for q in queries[:head])
    per_query = (time.perf_counter() - t0) / head if head else 0.0
    rest = queries[head:]

    # Parallel pays off when remaining > startup + remaining / workers.
    break_even = POOL_STARTUP_S * num_workers / max(1, num_workers - 1)
    if rest and per_query * len(rest) < break_even:
        raw.extend(_score_query(q, index, top_k) for q in rest)
    elif rest:
        # ~4 chunks per worker: dynamic balance without per-query IPC overhead.
        per_chunk = max(1, math.ceil(len(rest) / (num_workers * 4)))
        tasks = [(rest[a:b], top_k) for a, b in _ranges(len(rest), per_chunk)]
        pool = _make_pool(min(num_workers, len(tasks)), _set_index, index)
        try:
            for chunk in pool.imap(_search_range, tasks):
                raw.extend(chunk)
        finally:
            pool.terminate()
            pool.join()
            gc.unfreeze()
            _set_index(None)

    doc_titles = {d.doc_id: d.title for d in documents} if documents else {}
    results = [
        [SearchResult(doc_id=doc_id, score=score, title=doc_titles.get(doc_id, f"Document {doc_id}")) for doc_id, score in pairs]
        for pairs in raw
    ]

    elapsed = time.perf_counter() - start_time
    return results, elapsed


# ============================================================================
# Main Entry Point
# ============================================================================


def main():
    import argparse

    from document_generator import generate_corpus
    from sequential import batch_search_sequential, build_tfidf_index_sequential

    parser = argparse.ArgumentParser(description="Parallel TF-IDF indexing and search")
    parser.add_argument("--num-docs", type=int, default=5000)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--num-queries", type=int, default=200)
    args = parser.parse_args()

    documents = generate_corpus(args.num_docs, seed=42)
    seq = build_tfidf_index_sequential(documents)
    par = build_tfidf_index_parallel(documents, num_workers=args.num_workers)
    print(f"index: sequential {seq.elapsed_time:.3f}s parallel {par.elapsed_time:.3f}s speedup {seq.elapsed_time / par.elapsed_time:.2f}x")

    queries = [" ".join(d.title.split()[:2]) for d in documents[: args.num_queries]]
    t0 = time.perf_counter()
    batch_search_sequential(queries, seq.index, 10, documents)
    seq_t = time.perf_counter() - t0
    _, par_t = batch_search_parallel(queries, par.index, 10, args.num_workers, documents)
    print(f"search: sequential {seq_t:.3f}s parallel {par_t:.3f}s speedup {seq_t / par_t:.2f}x")


if __name__ == "__main__":
    main()
