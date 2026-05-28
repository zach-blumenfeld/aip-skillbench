---
name: map-optimization-strategy
description: Strategy for solving constraint optimization problems on spatial maps. Use when you need to place items on a grid/map to maximize some objective while satisfying constraints.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  A systematic three-phase approach to placement optimization problems on
  spatial maps: prune the search space, identify high-value spots, then
  anchor-search to find placements that capture those spots. Applies to
  any problem where items must be placed on a grid to maximize an
  objective under placement constraints. Avoids the combinatorial
  explosion of brute-force enumeration (O(M^N) for N items on M tiles).

trigger_when:
  - You must place N items on a grid/map to maximize an objective.
  - Placements are subject to hard constraints (terrain, range, blocked tiles).
  - Adjacency, clustering, or interaction effects between placements matter.
  - The candidate tile count makes exhaustive enumeration intractable.
  - A "center" or anchor constrains which tiles are reachable.

steps:
  - name: prune-search-space
    description: >
      Eliminate tiles that cannot contribute to a good solution. Remove
      tiles that are (a) invalid for any placement — violate hard
      constraints (wrong terrain, out of range, blocked); (b) dominated —
      another tile is strictly better in all respects; or (c) isolated —
      too far from other valid tiles to form useful clusters. This phase
      alone typically reduces the search space by 70–90% (e.g., 100
      candidate tiles down to 20–30). Prune early and aggressively —
      every tile removed saves exponential work in later phases.

  - name: score-and-rank-tiles
    description: >
      Score each surviving tile to find ones offering exceptional value.
      Score on three components: (1) intrinsic value — what the tile
      contributes on its own; (2) adjacency potential — bonuses from
      neighboring tiles; (3) cluster potential — whether the tile can
      anchor a high-value group. Sort descending and take the top-k as
      priority tiles. Example — Tile A with +4 base and +3 adjacency
      potential scores 7 (HIGH); Tile B with +1 base and +1 adjacency
      potential scores 2 (LOW). Any good solution likely includes several
      priority tiles.

  - name: anchor-search
    description: >
      Find placements that capture as many high-value spots as possible.
      (1) Select anchor candidates — tiles that enable access to multiple
      high-value spots. (2) Expand from each anchor greedily, adding the
      placement with the highest marginal value at each step. (3) Validate
      every placement against the full constraint set. (4) Apply local
      search — swap or move placements to look for improvements. Keep the
      best solution across all anchors tried. For problems with a "center"
      constraint (all placements within range of a central point), the
      anchor IS the center: try different center positions, and for each
      center the reachable high-value tiles are fixed — optimize placement
      within that center's reach.

decisions:
  - signal: The problem has a "center" constraint — all placements must lie within range of a single central point.
    action: Treat the anchor as the center. Iterate over candidate center positions; for each, the set of reachable high-value tiles is fixed, so optimize placement within that reach.

  - signal: Placing one item changes the value or validity of placing another (adjacency bonuses, mutual exclusion, blocking).
    action: Use constraint propagation — immediately update what's valid and what each remaining tile is worth after every placement, before choosing the next.

  - signal: A globally optimal solution would be expensive to prove or compute.
    action: Accept greedy expansion plus local search. A good local optimum found quickly beats a perfect solution found slowly.

  - signal: High-scoring tiles appear to cluster together on the map.
    action: Lean into it — adjacency bonuses compound, so good placements tend to be near other good placements. Prefer anchors that sit inside or next to high-value clusters.

scenarios:
  - need: Place N items on a map of M valid tiles to maximize an objective under placement constraints, without exhaustively enumerating O(M^N) combinations.
    context: >
      Algorithm skeleton in Python — three phases (prune, score, anchor
      search) composed into one routine.
    action: |
      def optimize_placements(map_tiles, constraints, num_placements):
          # Phase 1: Prune
          candidates = [t for t in map_tiles if is_valid_tile(t, constraints)]

          # Phase 2: Score and rank
          scored = [(tile, score_tile(tile, candidates)) for tile in candidates]
          scored.sort(key=lambda x: -x[1])  # Descending by score
          high_value = scored[:top_k]

          # Phase 3: Anchor search
          best_solution = None
          best_score = 0

          for anchor in get_anchor_candidates(high_value, constraints):
              solution = greedy_expand(anchor, candidates, num_placements, constraints)
              solution = local_search(solution, candidates, constraints)

              if solution.score > best_score:
                  best_solution = solution
                  best_score = solution.score

          return best_solution
    outcome: A near-optimal placement found in time polynomial in the pruned candidate count and the number of anchors tried, rather than exponential in the raw tile count.

anti_patterns:
  - Exhaustive brute-force enumeration of all placements — combinatorial explosion (O(M^N)) makes even small maps intractable (50 tiles × 5 items ≈ 312 million combinations), and most combinations are clearly suboptimal or invalid.
  - Ignoring interactions between placements — placing item A may change the value of placing item B (adjacency effects, mutual exclusion). Treating placements as independent leaves bonuses on the table.
  - Over-optimizing a single metric — squeezing the last point out of one tile can box you out of better placements for the remaining items. Balance intrinsic value with flexibility for what's still to come.
  - Skipping final validation — always verify the chosen solution satisfies ALL constraints before returning it; local search and greedy expansion can both produce candidates that look good but violate a hard constraint.
  - Skimping on pruning — every tile that survives Phase 1 multiplies work in Phases 2 and 3. Aggressive pruning is the highest-leverage optimization.
```
