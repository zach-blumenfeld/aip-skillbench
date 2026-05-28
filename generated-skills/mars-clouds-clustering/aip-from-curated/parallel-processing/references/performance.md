# joblib performance — what actually matters

## When parallelisation pays off

Parallel dispatch has a real cost: pickling arguments, spinning workers,
copying memory. The break-even is roughly:

- **Per-item work > 0.1 s.** Below that, the dispatch overhead dominates and
  sequential is faster.
- **Item count >= ~8.** Even with expensive per-item work, fanning out 2 or 3
  tasks rarely beats sequential after worker startup.

If both of those are unmet, just run sequentially.

## Backend choice

- `backend="loky"` (default) — separate processes. Use for CPU-bound work
  (numpy crunching, scoring, model fitting). Each worker is a fresh Python
  process, so the GIL is sidestepped.
- `backend="threading"` — threads in the same process. Use only when the
  worker spends most of its time waiting on I/O (HTTP, disk, GPU calls). For
  pure-Python CPU work, threading is killed by the GIL.

When in doubt, start with `loky`. Switch only when profiling shows the
workers are I/O-blocked.

## `n_jobs`

- `n_jobs=-1` — all cores. Default.
- `n_jobs=1` — sequential. Good for debugging; tracebacks point at the right
  line.
- `n_jobs=N` — exactly N workers. Cap below core count when sharing the
  machine or when each worker's memory footprint is large.

## Memory: the silent killer

Every loky worker gets a **pickled copy** of every argument you pass via
`delayed(...)(arg)`. For a 2 GB array and 16 workers that is 32 GB of RAM in
addition to the parent. Two mitigations:

1. Pre-compute and share at the module / closure level so the data is
   pickled once into the worker pool's shared memory map, not per call.
2. Pass a *handle* (filename, dataset id) instead of the data itself; let the
   worker load it.

If you see workers OOM-killed mid-run, this is almost always why.

## Progress visibility

`verbose=10` prints a percentage and ETA every batch. `verbose=50` prints
every task. `verbose=0` is silent. For long sweeps, `verbose=10` is the
default; it adds negligible overhead.

## Filtering and aggregation

Returning `None` from a worker is the idiomatic way to drop a combination
(e.g. clustering produced 0 valid clusters, parameters failed validation).
Filter at the end:

```python
results = [r for r in results if r is not None]
best = max(results, key=lambda r: r["score"])
```

## What to parallelise

Parallelise the **outer** loop — across items, hyperparameter cells, images,
chunks. Do *not* parallelise inside the worker. Nested parallelism either
oversubscribes the CPU (lots of context switching, slower overall) or fights
the GIL.

If your inner work is already vectorised (numpy / scipy / sklearn calling
into C), it is already using BLAS-level threading; adding joblib on top of
that wastes cores. In that case fan out only when the outer item count is
large enough that BLAS is underutilised.
