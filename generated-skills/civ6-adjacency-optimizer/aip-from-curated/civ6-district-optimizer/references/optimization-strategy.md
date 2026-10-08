# How the optimizer searches, and when to intervene

Load when `solution.search.exact` is false, the run is slow, or the task adds constraints
`optimize.py` does not model.

## Why not brute force

Placing N items on M tiles is O(M^N): 50 tiles and 5 items is ~312 million combinations, almost
all clearly bad or invalid. The search follows a prune / score / anchor strategy instead.

## What optimize.py does

1. **Prune** (Phase 1). Candidate tiles per district type = tiles within 3 of the center that
   civ6lib `PlacementRules.validate_placement` accepts (wrong terrain, out of range, blocked,
   occupied all removed). Dominated types are dropped: a Diplomatic Quarter is valid wherever an
   Encampment / Aerodrome / Preserve is and contributes the same, so those three are skipped.
2. **Score** (Phase 2). Each (type, tile) gets its stand-alone value (for ordering) and an
   optimistic bound: fixed sources around it plus the best district every free neighbor could
   hold, capped by how many districts can still be placed.
3. **Anchor search** (Phase 3). The anchor is the City Center: every valid center is tried
   (the start position first), and for each one a greedy solution seeds a branch-and-bound over
   district types in descending-value order. A branch is cut when its score plus the optimistic
   value of the remaining types (and what they could add to districts already placed) cannot
   beat the best total found on any center. With no timeout the result is optimal for the pool.
4. Unused specialty slots are filled with districts that do not lower the total, then
   everything is re-scored and validated with civ6lib verbatim.

Multi-city scenarios are solved city by city: each later city respects the minimum city
distance, the tiles already taken, and one-per-civilization districts.

## Key ideas (apply them if you adjust anything by hand)

- Prune early and aggressively; every tile removed saves exponential work.
- High-value tiles cluster: adjacency compounds, so good placements sit next to each other.
- Fixing the anchor (center) fixes which high-value tiles are reachable.
- Greedy + local search usually reaches a good optimum fast; the branch-and-bound proves it.
- Propagate constraints: placing one district changes what is valid and valuable for the rest.

## Pitfalls

- Ignoring interactions: placing A changes B's value (adjacency, destruction of Woods /
  Rainforest / bonus resources, occupied tiles).
- Over-optimizing one district instead of the total.
- Skipping validation: always check the final answer against every rule (`verify-answer`).

## When exact is false

The time limit (`time_limit_s`, default 240 s) stopped the search; the answer is the best found,
not proven optimal. If the task allows more time, rerun `optimize` with a larger
`time_limit_s` (raise the step timeout to match). Narrowing the pool (`allowed_districts`) or
fixing the center (`center_mode: given`) shrinks the search sharply.
