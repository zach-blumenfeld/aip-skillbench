# Map-reduce for global aggregates: TF-IDF, inverted indexes, counts

Load this when the target builds a global structure from per-item data: vocabulary, document frequencies, an inverted index, TF-IDF vectors, word counts, or histograms. Load it too when the target batch-scores queries against such a structure. These findings come from parallelizing a pure-Python TF-IDF build plus cosine search, with results identical to the sequential baseline (stdlib only, Python 3.12).

## Where the time goes

- Per-item work (regex tokenize, stop-word filter, term-frequency dict) is the only part that is independent per item. It parallelizes.
- Baselines often contain **O(V × D) passes**. Examples: `for term in vocabulary: sum(1 for d in docs if term in doc_terms[d])`, and building each posting list by rescanning every document. With a small vocabulary they look cheap, but they are still most of the serial time. Replace them with **one pass over the items**:
  - document frequency: `df = Counter(); for tf in tfs: df.update(tf.keys())`
  - posting lists, doc vectors and norms in the same loop over documents: `postings[term].append((doc_id, w))`
- After that fix, the parent's linear merge is the serial floor (Amdahl). On 10k documents the measured breakdown was: pool map 0.15 s at 8 workers, parent merge about 0.45 s, sequential baseline 2.2 s. The algorithmic fix alone gave 2× at 1 worker, and the total reached 3–4× at 4–8 workers.
- **Two-phase variants did not pay off.** In one variant, workers also computed doc vectors and postings after the parent broadcast the IDF. Pickling the vectors back cost as much as computing them in the parent. Keep one map phase (tokenize + TF) and a linear merge, unless measurement says otherwise.

## Build pattern (one map phase, linear merge)

```python
import math, multiprocessing as mp, os
from collections import Counter
from baseline import tokenize, compute_term_frequencies, TFIDFIndex, IndexingResult   # reuse the baseline's helpers

def _tf_chunk(chunk):                      # module-level -> picklable
    return [(doc_id, compute_term_frequencies(tokenize(text))) for doc_id, text in chunk]

def _ctx():
    try:
        return mp.get_context("fork")      # explicit: 3.14+/macOS default to spawn/forkserver
    except ValueError:
        return mp.get_context()

def build_parallel(documents, num_workers=None):
    num_workers = num_workers or os.cpu_count() or 1
    items = [(d.doc_id, d.title + " " + d.content) for d in documents]   # same text the baseline tokenizes
    if num_workers > 1 and len(items) > 1:
        chunks = lpt_chunks(items, [len(t) for _, t in items], num_workers * 4)   # balanced by text length
        with _ctx().Pool(num_workers) as pool:
            parts = pool.map(_tf_chunk, chunks)
        by_id = {}
        for part in parts:
            by_id.update(part)
        tfs = {d.doc_id: by_id[d.doc_id] for d in documents}          # restore BASELINE ITEM ORDER
    else:
        tfs = {doc_id: compute_term_frequencies(tokenize(t)) for doc_id, t in items}
    df = Counter()
    for tf in tfs.values():
        df.update(tf.keys())
    N = len(documents)
    idf = {t: math.log(N / c) + 1 for t, c in df.items()}             # same formula, same float ops
    postings = {t: [] for t in df}
    vectors, norms = {}, {}
    for doc_id, tf in tfs.items():                                     # baseline order -> identical ties and sums
        vec, ns = {}, 0.0
        for term, x in tf.items():                                     # tf dict order = baseline order
            w = x * idf[term]
            vec[term] = w
            ns += w * w
            postings[term].append((doc_id, w))
        vectors[doc_id], norms[doc_id] = vec, math.sqrt(ns)
    for pl in postings.values():
        pl.sort(key=lambda x: x[1], reverse=True)                      # stable: ties keep doc order like the baseline
    ...  # fill the baseline's index dataclass with the same field types (set vs dict vs list)
```

`lpt_chunks` sorts items by weight descending and puts each item in the lightest of k bins. It then returns each bin's items in their original order: see Strategy 4 in `references/balancing-strategies.md`. Document lengths are typically log-normal (many short, few very long). Contiguous equal-count chunks then leave workers idle, while LPT into about 4 chunks per worker stays under 1.1 imbalance.

## Exactness gotchas (each one caused a real mismatch)

- **Ties in sorted posting lists.** `list.sort` is stable, so the baseline's tie order is its insertion order: documents in input order. If you concatenate per-chunk lists in chunk order, sort by `(-score, position)` instead.
- **Float sums.** A norm is computed as `Σ w²` in the tf dict's insertion order (first occurrence of each token). Compute it the same way. Do not use `math.fsum`, sort the terms, or merge partial sums from chunks. Re-ordering changes the last bits, and tests that use `==` fail.
- **Cosine dot products.** The baseline sums `q[t] * d.get(t, 0)` over query terms in query order. Accumulating only the terms present, in the same order, gives identical floats (`x + 0.0 == x`).
- **Field types.** If the baseline's index has `vocabulary: set`, `idf: dict`, and `inverted_index: dict[str, list[tuple]]`, return exactly those types. Return the baseline's own dataclasses (import them), not look-alikes.
- **`num_documents`, `vocabulary_size`, `elapsed_time`.** Fill every field of the result object, including timing fields, the same way the baseline does.

## Batch search pattern

- Split the queries, not the index. Every worker needs the whole index read-only. Set it as a module global before creating a **fork** context pool, where it is inherited copy-on-write with no pickling. Under spawn, pass it once per worker through `Pool(initializer=_init, initargs=(index, documents))`. Never pass it with each task.
- Send queries in about 4 chunks per worker (`queries[i::n]` round-robin, or contiguous). Reassemble the results **in input order**.
- Per-query cost is small. For a few dozen queries on a small index, pool start-up and the index transfer under spawn exceed the gain. Fall back to a sequential loop when `num_workers == 1` or the batch is small. The measured gain was 3× on 200 queries over 10k documents with fork.
- Reuse the baseline's single-query search function inside the worker, so scores and tie-breaks are identical. Its `nlargest` over a set of candidate ids gives a deterministic order for the same index contents.

## Checklist for this workload

- [ ] Quadratic DF/posting loops replaced by one pass, giving the same values
- [ ] Workers do only tokenize + TF and receive `(id, text)` tuples
- [ ] Parent merge iterates documents in baseline order
- [ ] Index fields and types identical (`==` on every field against the baseline)
- [ ] Search results identical (doc ids and scores) for a varied query set, including queries with no known terms (empty result)
- [ ] Speedup measured at each required worker count on the task's corpus size
