"""Reusable joblib parallel patterns for grid search and batch work.

Three patterns the agent can import or adapt:

1. `parallel_map(func, items, n_jobs=-1, verbose=10, backend="loky")` —
   straight-line `func(item) for item in items` running in parallel.

2. `parallel_grid_search(evaluate, grid, n_jobs=-1, verbose=10, backend="loky")` —
   evaluate every combination in a parameter grid in parallel. `grid` is a
   dict mapping parameter name -> list of values; the cartesian product is
   passed to `evaluate(**combo)`. Results that come back as `None` (worker
   chose to skip) are filtered out; the rest are returned as a list of dicts.

3. `parallel_with_shared(func, items, shared, n_jobs=-1, verbose=10, backend="loky")` —
   pre-compute `shared` once and pass it positionally to every call of
   `func(item, shared)`. Use when each task needs the same large object
   (dataset, fitted estimator, lookup table) and recomputing it per worker
   would dominate cost. Note: with `backend="loky"` each worker still
   receives its own pickled copy; watch memory.

Performance heuristics enforced as guard rails:
- Skip parallelisation when item count is small (< MIN_ITEMS_FOR_PARALLEL).
- Skip parallelisation when an estimate of per-item cost is < MIN_PER_ITEM_SECONDS.

Both guards return the sequential result instead, so the call site does not
need to branch.
"""

from __future__ import annotations

from itertools import product
from typing import Any, Callable, Iterable, Mapping, Sequence

from joblib import Parallel, delayed

MIN_ITEMS_FOR_PARALLEL = 8
MIN_PER_ITEM_SECONDS = 0.1


def _should_parallelise(n_items: int, per_item_seconds: float | None) -> bool:
    if n_items < MIN_ITEMS_FOR_PARALLEL:
        return False
    if per_item_seconds is not None and per_item_seconds < MIN_PER_ITEM_SECONDS:
        return False
    return True


def parallel_map(
    func: Callable[[Any], Any],
    items: Sequence[Any],
    *,
    n_jobs: int = -1,
    verbose: int = 10,
    backend: str = "loky",
    per_item_seconds: float | None = None,
) -> list[Any]:
    """Parallel map. Falls back to sequential when not worth the overhead."""
    items = list(items)
    if not _should_parallelise(len(items), per_item_seconds):
        return [func(x) for x in items]
    return Parallel(n_jobs=n_jobs, verbose=verbose, backend=backend)(
        delayed(func)(x) for x in items
    )


def parallel_grid_search(
    evaluate: Callable[..., Mapping[str, Any] | None],
    grid: Mapping[str, Sequence[Any]],
    *,
    n_jobs: int = -1,
    verbose: int = 10,
    backend: str = "loky",
    per_item_seconds: float | None = None,
) -> list[Mapping[str, Any]]:
    """Run `evaluate(**combo)` over the cartesian product of `grid`.

    `evaluate` should return a dict including the parameter values and any
    scores, or `None` to drop that combination. Returned list has the `None`s
    filtered out.
    """
    keys = list(grid.keys())
    combos = [dict(zip(keys, values)) for values in product(*(grid[k] for k in keys))]
    if not _should_parallelise(len(combos), per_item_seconds):
        raw = [evaluate(**combo) for combo in combos]
    else:
        raw = Parallel(n_jobs=n_jobs, verbose=verbose, backend=backend)(
            delayed(evaluate)(**combo) for combo in combos
        )
    return [r for r in raw if r is not None]


def parallel_with_shared(
    func: Callable[[Any, Any], Any],
    items: Sequence[Any],
    shared: Any,
    *,
    n_jobs: int = -1,
    verbose: int = 10,
    backend: str = "loky",
    per_item_seconds: float | None = None,
) -> list[Any]:
    """Call `func(item, shared)` for every item in parallel.

    `shared` is computed once by the caller and passed positionally so every
    worker reuses the same value (each loky worker receives a pickled copy).
    """
    items = list(items)
    if not _should_parallelise(len(items), per_item_seconds):
        return [func(x, shared) for x in items]
    return Parallel(n_jobs=n_jobs, verbose=verbose, backend=backend)(
        delayed(func)(x, shared) for x in items
    )


def pick_best(results: Iterable[Mapping[str, Any]], score_key: str = "score") -> Mapping[str, Any]:
    """Return the result row with the maximum `score_key`. Raises on empty input."""
    results = list(results)
    if not results:
        raise ValueError("pick_best called with no results")
    return max(results, key=lambda r: r[score_key])
