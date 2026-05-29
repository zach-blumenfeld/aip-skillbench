# Algorithm details

Loaded on demand — only read when you need more than the SKILL.md body covers.

## Why exhaustive search fails

Placing N items on M valid tiles enumerates O(M^N) combinations.

- 50 tiles, 5 items ≈ 312 million combinations
- 100 tiles, 6 items ≈ 1 trillion

Most combinations are obviously suboptimal or invalid. Pruning + scoring + anchored search outperforms exhaustive search by orders of magnitude and reaches near-optimal results in practice.

## Phase 1 — pruning in depth

Three classes of tile to drop:

1. **Invalid** — fails a hard constraint (wrong terrain, out of range, blocked, occupied). Cheapest filter, run first.
2. **Dominated** — another tile is strictly >= on every relevant axis (intrinsic value, adjacency potential, accessibility) and strictly > on at least one. If `b` dominates `a`, no optimum includes `a`.
3. **Isolated** — too far from other valid tiles to participate in cluster bonuses. Use a distance threshold tuned to the problem (in Civ6: a tile with no other valid tile within 2 hexes contributes nothing to adjacency).

Expected reduction: 70–90 % of the raw tile set.

## Phase 2 — scoring components

Each candidate gets a composite score:

- **Intrinsic value** — what the tile contributes on its own (e.g. Campus on a tile next to two mountains gets +2 from the mountains before any other district is placed).
- **Adjacency potential** — the maximum bonus this tile could receive from neighbors if every neighbor were placed optimally. This is an upper bound, not a commitment.
- **Cluster potential** — does this tile anchor a high-value group? Sum the top-K neighbor scores.

A useful heuristic weighting: `score = intrinsic + 0.7 * adjacency_potential + 0.3 * cluster_potential`. Tune by what the objective rewards most.

Rank descending, keep the top-K (K ≈ 20 for typical 100-tile maps). These are your **priority tiles** — any good solution contains several of them.

## Phase 3 — anchor-point search

An **anchor** is a tile that unlocks access to many high-value tiles when fixed first. Anchor candidates are typically:

- The top 3–5 ranked tiles by Phase 2 score.
- For problems with a "center" constraint (Civ6: districts must be within 3 of the city center), every viable center is an anchor candidate.

For each anchor:

1. Seed the solution with the anchor.
2. **Greedy expand**: at each step, add the candidate that maximizes marginal value given current placements. Marginal value accounts for adjacency effects from already-placed items.
3. **Local search**: try swapping each placement against every unused candidate. Keep any swap that improves the total. Repeat until a full pass yields no improvement.

Return the best solution across all anchors.

## When the problem has a "center" constraint

For Civ6 specifically: every placement must lie within 3 hexes of the city center, AND the city center itself is a placement decision.

This makes the algorithm two-level:

1. **Outer loop**: enumerate candidate city-center tiles.
2. **Inner loop**: for each center, run Phase 1–3 over its reach (tiles within 3 hexes).

Candidate centers worth enumerating:
- Tiles adjacent to clusters of high-value resources.
- Tiles whose 3-hex reach contains the largest count of priority tiles.
- Tiles on rivers, near mountains, near coastal resources (multiple bonus paths converge).

Don't enumerate every tile — that defeats the pruning. Pick the top 5–10 center candidates by reach-coverage of priority tiles.

## Constraint propagation

After each placement, recompute validity for remaining candidates. Examples:

- Placing a district on a Woods tile destroys the Woods → adjacent Holy Sites lose the +0.5 bonus.
- Placing a Campus on a tile consumes that tile → it's no longer available for other districts.
- Filling a unique-district slot (one Campus per city) → all other Campus candidates are now infeasible.

If you don't propagate, the scoring becomes inconsistent and local search churns.

## Greedy + local search is usually enough

You do not need a provable global optimum. The problem structure (sparse high-value tiles + diminishing returns from clustering) means greedy expansion captures most of the value, and local search closes the gap to near-optimum in a handful of iterations.

If a problem is small (≤ 10 candidates after pruning), exhaustive enumeration is fine. If it's big and you have spare compute, run multiple random restarts of greedy+local-search and keep the best.

## Validate, always

Before returning a solution:

1. Every placement satisfies every hard constraint (terrain, range, uniqueness, district slots, special requirements).
2. Recompute the total score from scratch — don't trust an incrementally maintained running total.
3. If the problem has a known optimal or upper bound, log the gap.

A solution that scores high but violates a constraint is worth zero in most scoring rubrics.
