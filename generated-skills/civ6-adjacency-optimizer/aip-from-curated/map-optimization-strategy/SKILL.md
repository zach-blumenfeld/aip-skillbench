---
name: map-optimization-strategy
description: Strategy for solving constraint optimization problems on spatial maps. Use when placing items on a grid/hex map to maximize an objective under placement constraints — Civ6 district placement, adjacency-bonus maximization, facility siting, any problem with combinatorial placement choices where brute force is intractable.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Solve placement optimization on spatial maps with a prune -> score -> anchor-search
  strategy. The agent characterizes the problem, eliminates tiles that cannot
  contribute to a good solution, scores and ranks the survivors, then searches from
  promising anchors via greedy expansion plus local-swap refinement. Beats exhaustive
  search by orders of magnitude and reaches near-optimal results in practice.

trigger_when:
  - Placing N items on a grid or hex map to maximize an objective.
  - Solving a Civ6 district adjacency-bonus optimization (city center + districts).
  - The number of valid placements is large enough that brute force enumeration is intractable (e.g., M^N combinations).
  - The objective rewards spatial clustering or adjacency between placements.
  - There is a "center" or "hub" constraint that all placements must lie within range of.
  - Pairing with `civ6lib` (game rules) and `hex-grid-spatial` (coordinate math) to assemble a Civ6 solver.

do_not_use_when:
  - The problem is small enough (≤ ~10 candidates after trivial pruning) that direct enumeration is faster and gives an exact optimum.
  - The optimization is non-spatial — adjacency / neighbor effects do not drive the objective.
  - Placements are independent (no interaction effects) — sort by score and pick the top N.

scope_and_approval: >
  Read-only / compute-only. The skill produces a placement plan; it does not commit
  game actions, write files outside an `/output` path the caller specifies, or modify
  shared state. No approval gate needed before running the algorithm.

steps:
  - name: characterize-problem
    description: >
      Identify the objective function, hard constraints, number of placements, valid
      tile criteria, and any center / hub constraint. Decide what "intrinsic value",
      "adjacency potential", and "domination" mean for this objective. For Civ6,
      use `civ6lib` for placement rules and adjacency formulas.
    outputs:
      - name: problem-spec
        type: object
        description: "Objective fn, validity fn, scoring fns, num_placements, center constraint (if any)."

  - name: prune-search-space
    description: >
      Drop tiles that are invalid (hard-constraint violation), dominated (another tile
      is strictly better on every relevant axis), or isolated (too far from other valid
      tiles to form a useful cluster). Expect 70-90% reduction.
    script: scripts/optimize.py
    inputs:
      - name: problem-spec
        type: object
      - name: all-tiles
        type: list[object]
    outputs:
      - name: candidates
        type: list[object]
        description: "Surviving tiles worth considering. Function: `prune_candidates`."

  - name: score-and-rank
    description: >
      Score each candidate by intrinsic value + adjacency potential + cluster potential,
      sort descending, take the top-K (default K=20) as priority tiles. Tune the
      weighting to the objective.
    script: scripts/optimize.py
    inputs:
      - name: candidates
        type: list[object]
      - name: problem-spec
        type: object
    outputs:
      - name: ranked
        type: list[object]
        description: "Tile + score pairs, descending. Function: `score_and_rank`."
      - name: priority-tiles
        type: list[object]
        description: "Top-K ranked tiles."

  - name: enumerate-anchors
    description: >
      Choose anchor candidates — tiles that, if placed first, unlock access to many
      priority tiles. Defaults: top 3-5 ranked tiles. For a center-constrained problem,
      anchors ARE candidate centers: pick the 5-10 centers whose reach covers the most
      priority tiles, not every viable center.
    inputs:
      - name: ranked
        type: list[object]
      - name: problem-spec
        type: object
    outputs:
      - name: anchors
        type: list[object]

  - name: anchored-greedy-search
    description: >
      For each anchor, seed the solution with it, then greedily add candidates that
      maximize marginal value given current placements. Propagate constraints after
      each placement (adjacency effects, uniqueness, district slot counts). Skip
      anchors that fail to reach `num_placements` feasibly.
    script: scripts/optimize.py
    depends_on: [prune-search-space, score-and-rank, enumerate-anchors]
    inputs:
      - name: anchors
        type: list[object]
      - name: candidates
        type: list[object]
      - name: problem-spec
        type: object
    outputs:
      - name: greedy-solutions
        type: list[object]
        description: "One placement set per anchor. Function: `greedy_expand`."

  - name: local-search-refine
    description: >
      Try single-swap moves on each greedy solution. Keep any swap that improves the
      total score. Stop when a full pass yields no improvement or the iteration cap
      is hit. Closes the greedy-to-optimal gap.
    script: scripts/optimize.py
    inputs:
      - name: greedy-solutions
        type: list[object]
      - name: candidates
        type: list[object]
      - name: problem-spec
        type: object
    outputs:
      - name: refined-solutions
        type: list[object]
        description: "Function: `local_search`."

  - name: select-best
    description: >
      Pick the highest-scoring refined solution across all anchors. If the problem has
      a center constraint, the result includes both the chosen center and the placements.
    inputs:
      - name: refined-solutions
        type: list[object]
    outputs:
      - name: best-solution
        type: object

  - name: validate-and-finalize
    description: >
      Re-check every hard constraint on the chosen solution (terrain, range, uniqueness,
      district slots, special requirements). Recompute the total score from scratch —
      do not trust a running total. For Civ6, validate via `civ6lib.PlacementRules` and
      recompute via `civ6lib.AdjacencyCalculator`. If validation fails, fall back to the
      next-best solution. Emit the final result in the required output schema.
    inputs:
      - name: best-solution
        type: object
      - name: problem-spec
        type: object
    outputs:
      - name: final-output
        type: object

modes:
  - name: quick
    body: >
      Skip dominance and isolation filters in Phase 1; use only validity. Reduce top-K
      to 10. Use 3 anchors. Skip local search. Right for small maps or tight time budgets.
  - name: full
    body: >
      All three pruning filters, top-K=20-30, up to 10 anchors, local search to
      convergence. Right for hard instances where solution quality matters more than
      seconds of wall-clock.
  - name: center-search
    body: >
      Two-level: outer loop enumerates candidate centers (top 5-10 by reach-coverage of
      priority tiles), inner loop runs full prune -> score -> anchor-search within each
      center's reach. Use when the city / hub location is itself a decision variable.

integrations:
  - partner: civ6lib
    body: >
      Source the validity function from `civ6lib.PlacementRules.validate_placement`
      and the scoring/marginal/total functions from `civ6lib.AdjacencyCalculator`.
      Civ6 has a critical floor-each-source-separately rule for +0.5 adjacency
      sources — get this from `civ6lib`, do not re-derive it.
  - partner: hex-grid-spatial
    body: >
      Source neighbor lookup, hex distance, and tiles-in-range from `hex-grid-spatial`.
      Civ6 uses odd-r offset coordinates; even-row and odd-row neighbor offsets differ.
  - partner: sqlite-map-parser
    body: >
      For Civ6 .Civ6Map files (SQLite under the hood), extract the tile grid via
      `sqlite-map-parser` before running this strategy. The tile dictionaries it
      produces are the `all-tiles` input to Phase 1.

scenarios:
  - need: Civ6 single-city district placement, population 9, choose city center and up to 3 specialty districts to maximize total adjacency.
    context: >
      Map parsed via `sqlite-map-parser`. `civ6lib` provides validity and adjacency calculators.
      Cluster of mountains in the SW quadrant, river running E-W through the middle, coastal
      resources along the N edge.
    action: >
      Run mode=center-search. Outer loop picks 6 candidate centers covering the SW mountain
      cluster and the river. For each: prune to ~25 candidates within 3 hexes, score (Campus
      favors mountains, Commercial Hub favors river, Harbor favors coastal resources),
      take top-12, try 4 anchors each, greedy-expand to 3 districts, local-search.
    outcome: >
      Best solution: center on the river one hex from the mountain cluster; Campus adjacent
      to 3 mountains (+3); Commercial Hub on river (+2) adjacent to Campus (+0.5 floored=0);
      Harbor adjacent to city center (+2) and 1 coastal resource (+1). Total adjacency 8.
  - need: Generic facility-siting on a 100-cell grid, place 5 facilities, score = sum of intrinsic + neighbor bonuses.
    context: No center constraint; placements are independent of location class.
    action: >
      Run mode=full. Phase 1 prunes by validity + dominance only (no center => no isolation
      filter). Phase 2 ranks by intrinsic + max-possible-neighbor-bonus. Phase 3 uses the
      top 5 ranked tiles as anchors, greedy + local-search per anchor.
    outcome: >
      Returns the highest-scoring of 5 refined solutions. Wall-clock < 1 s for a 100-cell
      grid; gap to brute-force optimum typically < 3%.

anti_patterns:
  - Brute-force enumeration of all M-choose-N placements. Combinatorial explosion makes it intractable for any non-trivial map.
  - Skipping pruning. Every tile dropped early saves exponential work later.
  - Scoring only intrinsic value. Adjacency-driven objectives reward clustering; a tile with high standalone value but no good neighbors often loses to a moderately-valued tile in a high-potential cluster.
  - Ignoring placement interactions. Placing district A changes the value of placing district B (adjacency bonuses, destroyed Woods / Rainforest features, occupied tiles). Use a marginal-score function, not a static per-tile score.
  - Over-optimizing one metric. Squeezing every point from one placement can leave no good options for the remaining placements. Balance per-placement value against flexibility for what comes next.
  - Forgetting to validate the final solution against all hard constraints. A high-scoring invalid plan is worth zero in most scoring rubrics.
  - Trusting the incremental score. Always recompute the total from scratch on the final solution.
  - Enumerating every tile as a center candidate. Defeats the pruning. Pick the 5-10 centers with the best reach-coverage of priority tiles.
```
