"""Three-phase optimizer for placement problems on spatial maps.

Generic prune -> score -> anchor-search pipeline. Problem-specific logic
(validity, scoring, neighbor lookup) is injected as callables so the same
algorithm serves any constraint-optimization-on-a-grid task.

Public entry points:
    prune_candidates(tiles, is_valid, dominates=None, isolated=None)
    score_and_rank(tiles, score_fn) -> [(tile, score)]
    greedy_expand(seed, candidates, num_total, marginal_score_fn, is_valid_now)
    local_search(placements, candidates, score_solution, is_valid_now, iters)
    optimize_placements(...)  # orchestrates all phases

The greedy + local-search combination is intentionally a strong heuristic, not
a global optimum guarantee. It returns the best solution found across all
anchor seeds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional


Tile = Any  # opaque to this module; caller chooses the representation


@dataclass
class Solution:
    placements: list[Tile] = field(default_factory=list)
    score: float = 0.0
    meta: dict = field(default_factory=dict)


def prune_candidates(
    tiles: Iterable[Tile],
    is_valid: Callable[[Tile], bool],
    dominates: Optional[Callable[[Tile, Tile], bool]] = None,
    isolated: Optional[Callable[[Tile], bool]] = None,
) -> list[Tile]:
    """Phase 1: drop tiles that cannot contribute to a good solution.

    - is_valid: hard constraint check (terrain, range, blocked, etc.).
    - dominates(a, b): True if `a` is strictly >= `b` on every relevant axis
      and strictly > on at least one. When supplied, any tile dominated by
      another is removed.
    - isolated(t): True if `t` is too far from other valid tiles to form a
      useful cluster. Caller decides the threshold.
    """
    valid = [t for t in tiles if is_valid(t)]

    if isolated is not None:
        valid = [t for t in valid if not isolated(t)]

    if dominates is None:
        return valid

    survivors: list[Tile] = []
    for i, a in enumerate(valid):
        beaten = False
        for j, b in enumerate(valid):
            if i == j:
                continue
            if dominates(b, a):
                beaten = True
                break
        if not beaten:
            survivors.append(a)
    return survivors


def score_and_rank(
    tiles: Iterable[Tile],
    score_fn: Callable[[Tile], float],
) -> list[tuple[Tile, float]]:
    """Phase 2: score each tile, return descending by score."""
    scored = [(t, float(score_fn(t))) for t in tiles]
    scored.sort(key=lambda pair: -pair[1])
    return scored


def greedy_expand(
    seed: list[Tile],
    candidates: list[Tile],
    num_total: int,
    marginal_score_fn: Callable[[Tile, list[Tile]], float],
    is_valid_now: Callable[[Tile, list[Tile]], bool],
) -> list[Tile]:
    """Phase 3a: starting from `seed`, greedily add tiles up to num_total.

    `marginal_score_fn(tile, placed)` returns the value of adding `tile`
    given the current placements (so adjacency / interaction effects are
    captured). `is_valid_now(tile, placed)` enforces propagation of
    constraints as placements accumulate.
    """
    placed = list(seed)
    pool = [t for t in candidates if t not in placed]

    while len(placed) < num_total and pool:
        best: Optional[Tile] = None
        best_gain = float("-inf")
        for t in pool:
            if not is_valid_now(t, placed):
                continue
            gain = marginal_score_fn(t, placed)
            if gain > best_gain:
                best_gain = gain
                best = t
        if best is None:
            break
        placed.append(best)
        pool.remove(best)

    return placed


def local_search(
    placements: list[Tile],
    candidates: list[Tile],
    score_solution: Callable[[list[Tile]], float],
    is_valid_now: Callable[[Tile, list[Tile]], bool],
    iters: int = 50,
) -> list[Tile]:
    """Phase 3b: try single-swap moves to improve total score.

    Stops when a full pass over (placed_i, candidate_j) yields no improvement,
    or after `iters` improving moves.
    """
    current = list(placements)
    current_score = score_solution(current)

    for _ in range(iters):
        improved = False
        for i, p in enumerate(current):
            for c in candidates:
                if c in current:
                    continue
                trial = list(current)
                trial[i] = c
                # constraint check: remaining placements must still be valid
                if not _all_valid(trial, is_valid_now):
                    continue
                trial_score = score_solution(trial)
                if trial_score > current_score:
                    current = trial
                    current_score = trial_score
                    improved = True
                    break
            if improved:
                break
        if not improved:
            break

    return current


def _all_valid(
    placements: list[Tile],
    is_valid_now: Callable[[Tile, list[Tile]], bool],
) -> bool:
    for i, t in enumerate(placements):
        others = placements[:i] + placements[i + 1 :]
        if not is_valid_now(t, others):
            return False
    return True


def optimize_placements(
    tiles: Iterable[Tile],
    num_placements: int,
    is_valid: Callable[[Tile], bool],
    score_fn: Callable[[Tile], float],
    marginal_score_fn: Callable[[Tile, list[Tile]], float],
    is_valid_now: Callable[[Tile, list[Tile]], bool],
    score_solution: Callable[[list[Tile]], float],
    anchor_candidates: Optional[Callable[[list[tuple[Tile, float]]], list[Tile]]] = None,
    dominates: Optional[Callable[[Tile, Tile], bool]] = None,
    isolated: Optional[Callable[[Tile], bool]] = None,
    top_k: int = 20,
    local_search_iters: int = 50,
) -> Solution:
    """Full prune -> score -> anchor-search pipeline.

    Returns the best Solution found across all anchor seeds.
    """
    # Phase 1
    candidates = prune_candidates(tiles, is_valid, dominates=dominates, isolated=isolated)
    if not candidates:
        return Solution(meta={"reason": "no valid candidates after pruning"})

    # Phase 2
    ranked = score_and_rank(candidates, score_fn)
    high_value = [t for t, _ in ranked[:top_k]]

    # Phase 3
    if anchor_candidates is not None:
        seeds = anchor_candidates(ranked)
    else:
        seeds = high_value[: max(1, top_k // 4)]

    best = Solution(score=float("-inf"))

    for anchor in seeds:
        seed = [anchor] if anchor not in [] else []
        if not is_valid_now(anchor, []):
            continue
        placed = greedy_expand(
            seed=[anchor],
            candidates=candidates,
            num_total=num_placements,
            marginal_score_fn=marginal_score_fn,
            is_valid_now=is_valid_now,
        )
        if len(placed) < num_placements:
            continue
        placed = local_search(
            placements=placed,
            candidates=candidates,
            score_solution=score_solution,
            is_valid_now=is_valid_now,
            iters=local_search_iters,
        )
        s = score_solution(placed)
        if s > best.score:
            best = Solution(placements=placed, score=s, meta={"anchor": anchor})

    if best.score == float("-inf"):
        return Solution(meta={"reason": "no feasible solution found from any anchor"})
    return best


if __name__ == "__main__":
    # Tiny smoke test: place 3 items on a 1-D line of 20 cells where score
    # is position % 7 and adjacency penalty is 1 per neighbor.
    tiles = list(range(20))

    def is_valid(t):
        return True

    def score(t):
        return t % 7

    def marginal(t, placed):
        penalty = sum(1 for p in placed if abs(p - t) == 1)
        return score(t) - penalty

    def valid_now(t, placed):
        return t not in placed

    def total(placed):
        s = sum(score(p) for p in placed)
        penalty = sum(1 for i, a in enumerate(placed) for b in placed[i + 1 :] if abs(a - b) == 1)
        return s - penalty

    sol = optimize_placements(
        tiles=tiles,
        num_placements=3,
        is_valid=is_valid,
        score_fn=score,
        marginal_score_fn=marginal,
        is_valid_now=valid_now,
        score_solution=total,
        top_k=10,
    )
    print(f"smoke: placements={sol.placements} score={sol.score}")
