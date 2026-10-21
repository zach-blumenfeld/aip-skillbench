#!/usr/bin/env python3
"""
Verify a parallel TF-IDF solution against the sequential baseline: API, bit-identical
results, and speedup targets.

Requires: Python >= 3.9, standard library only. The workspace must contain
sequential.py, document_generator.py and parallel_solution.py.

Usage:
    python verify_parallel.py --workspace /root/workspace [--corpus corpus.json | --num-docs 3000]
                              [--workers 4] [--num-queries 200] [--top-k 10]
                              [--index-target 1.5] [--search-target 2.0] [--preflight-only]

Exit codes: 0 = API ok, results identical, both targets met
            1 = API problem or any result mismatch (correctness failure)
            2 = correct, but a speedup target was missed
Prints a human-readable log and, last, one JSON summary line prefixed "SUMMARY ".
"""

import argparse
import inspect
import json
import math
import os
import random
import sys
import time

REQUIRED_BASELINE = [
    "tokenize",
    "compute_term_frequencies",
    "TFIDFIndex",
    "SearchResult",
    "IndexingResult",
    "build_tfidf_index_sequential",
    "search_sequential",
    "batch_search_sequential",
]
INDEX_FIELDS = ["num_documents", "vocabulary", "document_frequencies", "idf", "inverted_index", "doc_vectors", "doc_norms"]
_REQUIRED = object()  # positional parameter without a default
EXPECTED_SIGS = {
    "build_tfidf_index_parallel": [("documents", _REQUIRED), ("num_workers", None), ("chunk_size", 500)],
    "batch_search_parallel": [("queries", _REQUIRED), ("index", _REQUIRED), ("top_k", 10), ("num_workers", None), ("documents", None)],
}


MAX_SHOWN = 8


def log(msg=""):
    print(msg, flush=True)


# ----------------------------------------------------------------------------
# Comparison helpers
# ----------------------------------------------------------------------------


def _max_float_diff(a, b):
    """Largest abs difference between matching floats in nested structures (None if shapes differ)."""
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b)
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return None
        diffs = [_max_float_diff(a[k], b[k]) for k in a]
    elif isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return None
        diffs = [_max_float_diff(x, y) for x, y in zip(a, b)]
    else:
        return 0.0 if a == b else None
    if any(d is None for d in diffs):
        return None
    return max(diffs, default=0.0)


DRIFT_TOL = 1e-9  # larger numeric gaps mean a different formula, not summation order


def _diff_kind(drift):
    if drift is None or drift == 0.0:
        return "structural/order difference: keys, lengths, ids or ordering differ"
    if drift <= DRIFT_TOL:
        return f"float drift only, max |diff| {drift:.1e}: arithmetic/summation order changed"
    return f"values differ, max |diff| {drift:.3e}: formula or inputs differ from the baseline"


def _first_diff(a, b, path="", limit=3):
    """Describe up to `limit` differences between two nested structures."""
    out = []
    if type(a) is not type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        return [f"{path}: type {type(a).__name__} != {type(b).__name__}"]
    if isinstance(a, dict):
        missing, extra = a.keys() - b.keys(), b.keys() - a.keys()
        if missing:
            out.append(f"{path}: {len(missing)} keys missing in parallel, e.g. {sorted(map(str, missing))[:3]}")
        if extra:
            out.append(f"{path}: {len(extra)} extra keys in parallel, e.g. {sorted(map(str, extra))[:3]}")
        for k in a.keys() & b.keys():
            if len(out) >= limit:
                break
            if a[k] != b[k]:
                out.extend(_first_diff(a[k], b[k], f"{path}[{k!r}]", limit - len(out)))
    elif isinstance(a, (list, tuple)):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} != {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            if len(out) >= limit:
                break
            if x != y:
                out.extend(_first_diff(x, y, f"{path}[{i}]", limit - len(out)))
    elif isinstance(a, set):
        out.append(f"{path}: sets differ (only baseline: {sorted(a - b)[:3]}, only parallel: {sorted(b - a)[:3]})")
    elif a != b:
        out.append(f"{path}: {a!r} != {b!r}")
    return out[:limit]


def compare_index(seq_idx, par_idx):
    problems = []
    for name in INDEX_FIELDS:
        if not hasattr(par_idx, name):
            problems.append(f"index.{name}: missing on parallel index")
            continue
        a, b = getattr(seq_idx, name), getattr(par_idx, name)
        if a != b:
            kind = _diff_kind(_max_float_diff(a, b))
            problems.append(f"index.{name}: MISMATCH ({kind}); " + "; ".join(_first_diff(a, b, name)))
    return problems


def _as_tuples(results):
    return [[(r.doc_id, r.score, r.title) for r in per_query] for per_query in results]


def compare_search(seq_res, par_res, queries):
    if not isinstance(par_res, list) or len(par_res) != len(seq_res):
        return [f"search: expected list of {len(seq_res)} result lists, got {type(par_res).__name__} len {len(par_res) if hasattr(par_res, '__len__') else '?'}"]
    a, b = _as_tuples(seq_res), _as_tuples(par_res)
    problems = []
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            kind = _diff_kind(_max_float_diff(x, y))
            problems.append(f"search query #{i} {queries[i]!r}: MISMATCH ({kind}); " + "; ".join(_first_diff(x, y, "results")))
            if len(problems) >= 5:
                problems.append("... (further query mismatches suppressed)")
                break
    return problems


# ----------------------------------------------------------------------------
# Inputs
# ----------------------------------------------------------------------------


def make_queries(index, n, seed):
    """Realistic queries from the corpus vocabulary plus edge cases the baseline handles specially."""
    rng = random.Random(seed)
    vocab = sorted(index.vocabulary)
    by_df = sorted(vocab, key=lambda t: (-index.document_frequencies[t], t))
    common, rare = by_df[: max(1, len(by_df) // 10)], by_df[len(by_df) // 2 :] or by_df
    edge = [
        "",  # no tokens -> []
        "the and of to in",  # only stop words -> []
        "zzqx qwertyuiop",  # unknown terms -> []
        "a b c",  # single letters are not tokens -> []
    ]
    if vocab:
        edge += [
            f"{vocab[0].upper()}, {vocab[-1].title()}!! 123",  # case/punctuation/digits
            " ".join(common[:3] * 3),  # repeated common terms (ties likely)
            rare[0],  # single rare term (fewer than top_k candidates possible)
            " ".join(rng.sample(vocab, min(12, len(vocab)))),  # long query
        ]
    queries = list(edge)
    while vocab and len(queries) < n:
        k = rng.randint(1, 5)
        pool = common if rng.random() < 0.5 else vocab
        queries.append(" ".join(rng.choice(pool) for _ in range(k)))
    return queries[: max(n, len(edge))] if vocab else queries


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------


def check_signatures(par):
    problems = []
    for fname, expected in EXPECTED_SIGS.items():
        fn = getattr(par, fname, None)
        if fn is None:
            problems.append(f"parallel_solution.{fname} is missing")
            continue
        params = list(inspect.signature(fn).parameters.values())
        for i, (pname, default) in enumerate(expected):
            if i >= len(params) or params[i].name != pname:
                got = params[i].name if i < len(params) else "<none>"
                problems.append(f"{fname}: parameter #{i} should be '{pname}', got '{got}'")
                continue
            if default is _REQUIRED:
                continue
            have = params[i].default
            if have is inspect.Parameter.empty or have != default:
                problems.append(f"{fname}: '{pname}' default should be {default!r}, got {'none' if have is inspect.Parameter.empty else repr(have)}")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", required=True, help="Directory with sequential.py and parallel_solution.py")
    ap.add_argument("--corpus", help="Corpus JSON (document_generator.save_corpus format); else generate")
    ap.add_argument("--num-docs", type=int, default=3000, help="Docs to generate when no --corpus (default 3000)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--num-queries", type=int, default=200)
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--index-target", type=float, default=1.5)
    ap.add_argument("--search-target", type=float, default=2.0)
    ap.add_argument("--preflight-only", action="store_true", help="Only check imports and signatures")
    args = ap.parse_args()

    ws = os.path.abspath(args.workspace)
    sys.path.insert(0, ws)
    summary = {"workspace": ws, "cpu_count": os.cpu_count(), "workers": args.workers, "problems": []}

    def finish(code):
        summary["exit_code"] = code
        log("SUMMARY " + json.dumps(summary, default=str))
        sys.exit(code)

    # --- Preflight -----------------------------------------------------------
    for f in ("sequential.py", "document_generator.py", "parallel_solution.py"):
        if not os.path.isfile(os.path.join(ws, f)):
            summary["problems"].append(f"missing {os.path.join(ws, f)}")
    if summary["problems"]:
        log("\n".join(summary["problems"]))
        finish(1)
    import document_generator as dg  # noqa: E402
    import sequential as seq  # noqa: E402

    missing = [n for n in REQUIRED_BASELINE if not hasattr(seq, n)]
    if missing:
        summary["problems"].append(f"sequential.py lacks {missing}: baseline differs from the template's assumptions")
    try:
        import parallel_solution as par  # noqa: E402
    except Exception as e:  # noqa: BLE001
        summary["problems"].append(f"import parallel_solution failed: {type(e).__name__}: {e}")
        log("\n".join(summary["problems"]))
        finish(1)
    summary["problems"] += check_signatures(par)
    log(f"Preflight: cpu_count={os.cpu_count()} workers={args.workers} python={sys.version.split()[0]}")
    if summary["problems"]:
        log("PREFLIGHT FAILED:\n  " + "\n  ".join(summary["problems"]))
        finish(1)
    log("Preflight OK: baseline names present, parallel API signatures match")
    if args.preflight_only:
        finish(0)
    if os.cpu_count() and os.cpu_count() < args.workers:
        log(f"WARNING: only {os.cpu_count()} CPUs for {args.workers} workers; speedups will be capped")
        summary["cpu_limited"] = True

    # --- Corpus --------------------------------------------------------------
    t0 = time.perf_counter()
    docs = dg.load_corpus(args.corpus) if args.corpus else dg.generate_corpus(args.num_docs, seed=args.seed)
    summary["num_docs"] = len(docs)
    log(f"Corpus: {len(docs)} docs, {sum(d.word_count for d in docs):,} words ({time.perf_counter() - t0:.1f}s to load)")

    # --- Index build ---------------------------------------------------------
    log("Building sequential index ...")
    t0 = time.perf_counter()
    s_res = seq.build_tfidf_index_sequential(docs)
    s_time = time.perf_counter() - t0
    log(f"  sequential: {s_time:.3f}s, vocab {s_res.vocabulary_size}")

    log(f"Building parallel index (num_workers={args.workers}) ...")
    t0 = time.perf_counter()
    p_res = par.build_tfidf_index_parallel(docs, num_workers=args.workers)
    p_time = time.perf_counter() - t0
    log(f"  parallel:   {p_time:.3f}s (reported elapsed_time {getattr(p_res, 'elapsed_time', float('nan')):.3f}s)")

    problems = []
    if type(p_res).__name__ != "ParallelIndexingResult":
        problems.append(f"build_tfidf_index_parallel returned {type(p_res).__name__}, expected ParallelIndexingResult")
    for attr in ("index", "elapsed_time", "num_documents", "vocabulary_size"):
        if not hasattr(p_res, attr):
            problems.append(f"ParallelIndexingResult lacks .{attr}")
    if problems:
        summary["problems"] += problems
        log("\n".join(problems))
        finish(1)
    if not isinstance(p_res.index, seq.TFIDFIndex):
        problems.append(f"result.index is {type(p_res.index).__name__}, not sequential.TFIDFIndex")
    if p_res.num_documents != s_res.num_documents or p_res.vocabulary_size != s_res.vocabulary_size:
        problems.append(f"counts differ: num_documents {p_res.num_documents} vs {s_res.num_documents}, vocabulary_size {p_res.vocabulary_size} vs {s_res.vocabulary_size}")
    problems += compare_index(s_res.index, p_res.index)
    log("  index identical: " + ("YES" if not problems else "NO"))

    # Other configurations must give the same index too.
    subset = docs[: min(len(docs), 150)]
    sub_ref = seq.build_tfidf_index_sequential(subset).index
    for label, kwargs in [
        ("num_workers=1", {"num_workers": 1}),
        ("num_workers=None", {"num_workers": None}),
        ("chunk_size=7", {"num_workers": args.workers, "chunk_size": 7}),
    ]:
        sub = par.build_tfidf_index_parallel(subset, **kwargs)
        diffs = compare_index(sub_ref, sub.index)
        log(f"  {len(subset)}-doc subset, {label}: " + ("identical" if not diffs else "MISMATCH"))
        problems += [f"[subset {label}] {d}" for d in diffs]
    big_chunk = par.build_tfidf_index_parallel(docs, num_workers=args.workers, chunk_size=max(1, len(docs) // 3))
    diffs = compare_index(s_res.index, big_chunk.index)
    log(f"  full corpus, chunk_size={max(1, len(docs) // 3)}: " + ("identical" if not diffs else "MISMATCH"))
    problems += [f"[chunk_size large] {d}" for d in diffs]
    try:
        empty_seq = seq.build_tfidf_index_sequential([])
        empty_par = par.build_tfidf_index_parallel([], num_workers=args.workers)
        diffs = compare_index(empty_seq.index, empty_par.index)
        log("  empty corpus: " + ("identical" if not diffs else "MISMATCH"))
        problems += [f"[empty corpus] {d}" for d in diffs]
    except Exception as e:  # noqa: BLE001
        problems.append(f"[empty corpus] parallel raised {type(e).__name__}: {e}")

    # --- Search --------------------------------------------------------------
    queries = make_queries(s_res.index, args.num_queries, args.seed)
    summary["num_queries"] = len(queries)
    log(f"Searching {len(queries)} queries (top_k={args.top_k}) ...")
    t0 = time.perf_counter()
    s_search = seq.batch_search_sequential(queries, s_res.index, args.top_k, docs)
    ss_time = time.perf_counter() - t0
    log(f"  sequential: {ss_time:.3f}s")
    t0 = time.perf_counter()
    out = par.batch_search_parallel(queries, s_res.index, top_k=args.top_k, num_workers=args.workers, documents=docs)
    ps_time = time.perf_counter() - t0
    if not (isinstance(out, tuple) and len(out) == 2 and isinstance(out[1], (int, float))):
        problems.append(f"batch_search_parallel must return (results, elapsed_time); got {type(out).__name__}")
        p_search = out[0] if isinstance(out, (tuple, list)) and out else out
    else:
        p_search = out[0]
        log(f"  parallel:   {ps_time:.3f}s (reported elapsed_time {out[1]:.3f}s)")
    search_problems = compare_search(s_search, p_search, queries)
    log("  search results identical: " + ("YES" if not search_problems else "NO"))
    problems += search_problems

    # Parallel index + parallel search, no titles, other worker counts, tiny batches.
    for label, q, kw, ref_docs in [
        ("parallel index, documents=None", queries[:60], {"num_workers": args.workers}, None),
        ("num_workers=1", queries[:20], {"num_workers": 1}, docs),
        ("num_workers=None", queries[:40], {"num_workers": None}, docs),
        ("top_k=3", queries[:40], {"num_workers": args.workers, "top_k": 3}, docs),
        ("2 queries", queries[5:7], {"num_workers": args.workers}, docs),
        ("0 queries", [], {"num_workers": args.workers}, docs),
    ]:
        idx = p_res.index if label.startswith("parallel index") else s_res.index
        k = kw.pop("top_k", args.top_k)
        ref = seq.batch_search_sequential(q, s_res.index, k, ref_docs)
        got = par.batch_search_parallel(q, idx, top_k=k, documents=ref_docs, **kw)
        diffs = compare_search(ref, got[0] if isinstance(got, tuple) else got, q)
        log(f"  {label}: " + ("identical" if not diffs else "MISMATCH"))
        problems += [f"[{label}] {d}" for d in diffs]

    summary["problems"] += problems
    summary["index_seconds"] = {"sequential": round(s_time, 4), "parallel": round(p_time, 4)}
    summary["search_seconds"] = {"sequential": round(ss_time, 4), "parallel": round(ps_time, 4)}
    idx_speedup = s_time / p_time if p_time > 0 else math.inf
    srch_speedup = ss_time / ps_time if ps_time > 0 else math.inf
    summary["index_speedup"] = round(idx_speedup, 2)
    summary["search_speedup"] = round(srch_speedup, 2)
    summary["index_target_met"] = idx_speedup >= args.index_target
    summary["search_target_met"] = srch_speedup >= args.search_target
    log(f"Index speedup:  {idx_speedup:.2f}x (target {args.index_target}x) {'OK' if summary['index_target_met'] else 'MISSED'}")
    log(f"Search speedup: {srch_speedup:.2f}x (target {args.search_target}x) {'OK' if summary['search_target_met'] else 'MISSED'}")

    if problems:
        shown = problems[:MAX_SHOWN]
        more = f"\n  ... and {len(problems) - MAX_SHOWN} more" if len(problems) > MAX_SHOWN else ""
        log(f"CORRECTNESS FAILED ({len(problems)} problems):\n  " + "\n  ".join(shown) + more)
        summary["problems"] = summary["problems"][:MAX_SHOWN]
        summary["num_problems"] = len(problems)
        finish(1)
    log("Correctness: all results identical to the baseline")
    finish(0 if summary["index_target_met"] and summary["search_target_met"] else 2)


if __name__ == "__main__":
    main()
