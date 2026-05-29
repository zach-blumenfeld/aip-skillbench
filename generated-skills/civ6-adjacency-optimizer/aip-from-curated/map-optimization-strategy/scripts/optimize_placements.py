"""Three-phase optimizer for placement problems on spatial maps.

This is the reusable skeleton from `map-optimization-strategy`: prune the
search space, score and rank surviving tiles, then run an anchor-driven
search over the high-value subset. Domain logic (validity, scoring,
expansion, local moves) is supplied by the caller as callables — keep
those problem-specific. The orchestration here is fixed.

Typical wiring for Civ6 adjacency optimization:
    - `is_valid(tile, ctx)` — terrain check + within-city-range + not-taken
    - `score(tile, candidates, ctx)` — base district yield + adjacency
        bonuses from neighbors (use `hex-grid-spatial` for neighbor sets)
    - `get_anchor_candidates(top_tiles, ctx)` — city-center positions
        that bring the most high-value tiles inside their workable radius
    - `greedy_expand(anchor, candidates, k, ctx)` — pick the best k
        non-conflicting districts inside the anchor's reach
    - `local_search(solution, candidates, ctx)` — swap / relocate / drop
        districts to improve total adjacency
    - `is_dominated`, `is_isolated` — optional pruning predicates; if
        omitted, only `is_valid` filters tiles

The return is whichever Solution object `greedy_expand` produced. The
optimizer requires only that it carry a `.score` (numeric) attribute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Protocol


class Solution(Protocol):
    score: float


@dataclass
class OptimizationResult:
    solution: Optional[Any]
    score: float
    candidates_before: int
    candidates_after_prune: int
    high_value_count: int
    anchors_tried: int
    anchors_improved: int


def optimize_placements(
    tiles: Iterable[Any],
    num_placements: int,
    *,
    is_valid: Callable[[Any, Any], bool],
    score: Callable[[Any, list, Any], float],
    get_anchor_candidates: Callable[[list, Any], Iterable[Any]],
    greedy_expand: Callable[[Any, list, int, Any], Optional[Any]],
    local_search: Optional[Callable[[Any, list, Any], Any]] = None,
    is_dominated: Optional[Callable[[Any, list, Any], bool]] = None,
    is_isolated: Optional[Callable[[Any, list, Any], bool]] = None,
    context: Any = None,
    top_k: Optional[int] = None,
) -> OptimizationResult:
    """Run the three-phase placement optimizer.

    `tiles` is the full map. `num_placements` is the number of items to
    place. The callable arguments encode domain logic — see the module
    docstring for the Civ6 wiring. `top_k` caps the size of the
    high-value working set passed into anchor search; defaults to
    `max(num_placements * 4, 12)`.
    """
    tiles = list(tiles)
    candidates_before = len(tiles)

    # Phase 1: Prune.
    candidates = [t for t in tiles if is_valid(t, context)]
    if is_dominated is not None:
        candidates = [t for t in candidates if not is_dominated(t, candidates, context)]
    if is_isolated is not None:
        candidates = [t for t in candidates if not is_isolated(t, candidates, context)]
    candidates_after_prune = len(candidates)

    if not candidates:
        return OptimizationResult(
            solution=None,
            score=0.0,
            candidates_before=candidates_before,
            candidates_after_prune=0,
            high_value_count=0,
            anchors_tried=0,
            anchors_improved=0,
        )

    # Phase 2: Score and rank.
    scored = sorted(
        ((t, score(t, candidates, context)) for t in candidates),
        key=lambda x: -x[1],
    )
    if top_k is None:
        top_k = max(num_placements * 4, 12)
    high_value = [t for t, _ in scored[:top_k]]

    # Phase 3: Anchor-point search with optional local refinement.
    best: Optional[Any] = None
    best_score = float("-inf")
    anchors_tried = 0
    anchors_improved = 0

    for anchor in get_anchor_candidates(high_value, context):
        anchors_tried += 1
        solution = greedy_expand(anchor, candidates, num_placements, context)
        if solution is None:
            continue
        if local_search is not None:
            solution = local_search(solution, candidates, context)
        s = float(solution.score)
        if s > best_score:
            best = solution
            best_score = s
            anchors_improved += 1

    return OptimizationResult(
        solution=best,
        score=best_score if best is not None else 0.0,
        candidates_before=candidates_before,
        candidates_after_prune=candidates_after_prune,
        high_value_count=len(high_value),
        anchors_tried=anchors_tried,
        anchors_improved=anchors_improved,
    )


if __name__ == "__main__":
    print(
        "optimize_placements.py is a library. Import "
        "`optimize_placements` from this module and pass domain-specific "
        "callables (is_valid, score, get_anchor_candidates, greedy_expand, "
        "local_search) tuned to the problem at hand."
    )
