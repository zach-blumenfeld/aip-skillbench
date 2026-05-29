---
name: map-optimization-strategy
description: Strategy for solving placement/constraint optimization problems on spatial maps — place N items on a grid (hex or square) to maximize a scoring objective while satisfying terrain, range, and exclusivity constraints. Use when the search space is too large for exhaustive enumeration (e.g., Civ6 district adjacency optimization, facility siting, resource collector placement on hex maps, any item-on-tile problem with adjacency bonuses or coverage constraints). Encodes a three-phase approach — prune dominated/invalid/isolated tiles, score and rank the survivors, then run an anchor-driven greedy + local search over the high-value subset.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Python 3.9+ recommended for the bundled `scripts/optimize_placements.py` skeleton. Pure algorithmic strategy — no external libraries, network, or filesystem requirements at the strategy layer. Domain wiring (tile data, validity rules, scoring) is supplied by the caller, typically through sibling skills such as `civ6lib`, `hex-grid-spatial`, and `sqlite-map-parser`.
---

```yaml
purpose: >
  Solve placement-on-map optimization problems without falling into the
  exhaustive-search trap. Combinatorial enumeration is O(M^N) in the
  number of candidate tiles M and items N; even a 50-tile / 5-item
  problem is 312M combinations, and real Civ6-style maps are larger.
  This skill encodes a three-phase strategy — aggressive pruning,
  value-aware ranking, and anchor-driven greedy + local search — that
  finds strong (typically near-optimal) solutions in seconds. The
  algorithm skeleton lives in `scripts/optimize_placements.py` and
  accepts domain-specific callables (validity, scoring, anchor
  generation, expansion, local moves) so the same orchestration drives
  Civ6 adjacency optimization, facility siting, or any item-on-tile
  problem with adjacency bonuses or coverage constraints.

trigger_when:
  - Placing N items on a grid/map to maximize an objective subject to placement constraints (terrain, range from a center, exclusivity, capacity).
  - Civ6-style adjacency optimization — choosing city-center and district positions to maximize total adjacency bonuses.
  - The candidate search space is large enough that exhaustive enumeration is intractable (more than ~10^5 raw combinations).
  - Adjacency / neighborhood interactions matter — placing one item changes the marginal value of placing another nearby.
  - The problem has a "center" constraint where every placement must lie within a fixed radius of an anchor (e.g., city workable range).
  - User mentions district placement, adjacency bonuses, hex-grid optimization, facility siting, sensor placement, or constraint-satisfaction on a spatial map.

do_not_use_when:
  - The exact solution can be enumerated cheaply (e.g., < 10^4 combinations) — just enumerate; the heuristic loses the global-optimum guarantee.
  - The problem has no spatial / adjacency structure — pure assignment or matching problems are better served by ILP, the Hungarian algorithm, or min-cost-flow.
  - A specialized solver is already wired (OR-Tools CP-SAT, Gurobi). Use the solver; this skill encodes a heuristic, not a guarantee.
  - The objective is non-decomposable (e.g., depends on the full configuration through a learned function) and per-tile scoring cannot give a useful ranking signal.

scope_and_approval: >
  Read-only with respect to the map and game state. The skill produces
  a placement plan; writing the plan to the task's output JSON or
  applying it in-game is the caller's responsibility. Safe to run
  without prompting. The optimizer is deterministic given deterministic
  callables — same inputs produce the same plan, which makes it safe
  inside reproducibility-sensitive scoring loops.

steps:
  - name: model-the-problem
    description: >
      Before invoking the strategy, name the four problem-specific
      pieces the skeleton needs as callables&#58; (1) `is_valid(tile,
      ctx)` — terrain/range/exclusivity hard constraints; (2)
      `score(tile, candidates, ctx)` — intrinsic + adjacency + cluster
      potential; (3) `get_anchor_candidates(top_tiles, ctx)` — where
      can a center/workable region sit such that it reaches many high
      value tiles; (4) `greedy_expand(anchor, candidates, k, ctx)` and
      optional `local_search`. For Civ6, the anchors are candidate
      city-center positions and the radius is the workable range; the
      scorer combines intrinsic district yield with the adjacency rules
      from `civ6lib` over the hex neighbors from `hex-grid-spatial`.
    outputs:
      - name: problem-model
        type: object
        description: A bundle of callables and the context object passed through to all of them (game state, tile data, constraint parameters).
  - name: prune-search-space
    description: >
      Eliminate tiles that cannot contribute to a good solution before
      any scoring or search runs. Three filters, in order&#58; (a)
      hard-constraint invalid (wrong terrain, out of range from any
      legal anchor, blocked / already occupied); (b) dominated — some
      other tile is strictly better on every dimension the scorer
      consults; (c) isolated — too far from other valid tiles to ever
      anchor or join a high-value cluster. Aggressive pruning typically
      removes 70-90 percent of the raw tile set and is the single
      biggest lever on wall-clock and solution quality.
    script: scripts/optimize_placements.py
    depends_on: [model-the-problem]
    inputs:
      - name: tiles
        type: list[object]
        description: All candidate tiles from the map (output of `sqlite-map-parser` for Civ6).
      - name: is_valid
        type: object
        description: Callable `(tile, ctx) -> bool` encoding hard constraints.
      - name: is_dominated
        type: object
        nullable: true
        description: Optional callable `(tile, candidates, ctx) -> bool` for the dominance filter.
      - name: is_isolated
        type: object
        nullable: true
        description: Optional callable `(tile, candidates, ctx) -> bool` for the isolation filter.
    outputs:
      - name: candidates
        type: list[object]
        description: Pruned tile set passed into scoring and anchor search.
  - name: score-and-rank-tiles
    description: >
      Score each surviving tile with three components — intrinsic
      value (what this tile yields on its own), adjacency potential
      (what bonuses it would earn from its current neighbors), and
      cluster potential (whether it could anchor or join a high-value
      group). Rank descending and keep the top-K as the high-value
      working set. The skeleton uses `top_k = max(num_placements * 4,
      12)` by default; raise it when adjacency bonuses are large
      relative to intrinsic yield (more neighbors matter), lower it
      when the optimization budget is tight.
    script: scripts/optimize_placements.py
    depends_on: [prune-search-space]
    inputs:
      - name: candidates
        type: list[object]
      - name: score
        type: object
        description: Callable `(tile, candidates, ctx) -> float` returning the per-tile score.
      - name: top_k
        type: integer
        nullable: true
        description: Working-set size cap for the anchor phase.
    outputs:
      - name: high_value
        type: list[object]
        description: Top-K tiles ranked by score, fed to the anchor-search phase.
  - name: anchor-point-search
    description: >
      For each candidate anchor — typically a tile that brings many
      high-value tiles inside the placement reach — run a greedy
      expansion that picks placements maximizing marginal score subject
      to constraints, then an optional local search that swaps,
      relocates, or drops placements to improve the total. Track the
      best solution seen across anchors. For Civ6, the anchor IS the
      city center; iterating over anchors means iterating over candidate
      city-center positions, and each anchor's reachable high-value
      tiles are fixed once the radius is known.
    script: scripts/optimize_placements.py
    depends_on: [score-and-rank-tiles]
    inputs:
      - name: high_value
        type: list[object]
      - name: candidates
        type: list[object]
      - name: num_placements
        type: integer
      - name: get_anchor_candidates
        type: object
        description: Callable `(top_tiles, ctx) -> Iterable[anchor]` enumerating anchor positions to try.
      - name: greedy_expand
        type: object
        description: Callable `(anchor, candidates, num_placements, ctx) -> Solution` doing per-anchor greedy placement.
      - name: local_search
        type: object
        nullable: true
        description: Optional callable `(solution, candidates, ctx) -> Solution` refining a greedy solution.
    outputs:
      - name: best_solution
        type: object
        description: The highest-scoring solution found across all anchors. Carries `.score` plus whatever placement structure `greedy_expand` returned.
  - name: validate-and-emit
    description: >
      Re-verify the chosen solution against ALL hard constraints —
      terrain, range, exclusivity, count — before treating it as
      final. The pruning phase makes per-tile validity decisions; this
      step confirms the *configuration* is valid (no two districts on
      the same tile, district count matches the population cap, every
      placement still inside the chosen city's reach after the final
      anchor was fixed). Emit the solution in the task's expected
      output schema; for the Civ6 task, that is
      `/output/scenario_3.json` with `city_center`, `placements`,
      `adjacency_bonuses`, and `total_adjacency`, where the sum of
      `adjacency_bonuses` must equal `total_adjacency`.
    depends_on: [anchor-point-search]
    inputs:
      - name: best_solution
        type: object
    outputs:
      - name: validated-plan
        type: object
        description: A plan ready for serialization to the task's output format.

modes:
  - name: library
    body: >
      Import the skeleton directly&#58;
      `from optimize_placements import optimize_placements` and pass
      problem-specific callables plus a `context` object. The
      orchestrator returns an `OptimizationResult` with the best
      `solution`, its `score`, and pruning / anchor diagnostics — use
      the diagnostics to verify pruning was aggressive enough
      (`candidates_after_prune` should typically be 10-30 percent of
      `candidates_before`) and that more than one anchor was tried.
  - name: ad-hoc
    body: >
      For a one-shot problem, the agent may inline the same three-phase
      loop directly in `solution.py` rather than import the skeleton.
      Keep the phase ordering identical&#58; prune before scoring, score
      before anchor search, and validate the final configuration
      end-to-end. The skeleton mainly exists to keep the phase
      ordering correct under iteration pressure — inline code that
      collapses phases (e.g. scoring during enumeration) typically
      degrades into exhaustive search.

scenarios:
  - need: Civ6 single-city adjacency optimization on a hex map — place one city center plus N districts to maximize total adjacency.
    context: "`sqlite-map-parser` yields the tile list; `hex-grid-spatial` provides hex neighbor sets; `civ6lib` provides the district yield and adjacency rule tables. Map has ~100 tiles, valid terrain narrows to ~40, the workable radius is 3."
    action: >
      Wire `is_valid` against the terrain / range tables from
      `civ6lib`, `score` against intrinsic district yield plus
      adjacency over `hex-grid-spatial` neighbor sets, and
      `get_anchor_candidates` to enumerate plausible city-center hexes
      among the top-scored tiles. Call `optimize_placements(tiles,
      num_placements, ...)`. Validate that the placement count matches
      the task's `population`, write `city_center`, `placements`,
      per-district `adjacency_bonuses`, and `total_adjacency` to
      `/output/scenario_3.json`.
    outcome: A single best plan with per-district bonus breakdown summing exactly to `total_adjacency`, written in seconds even on a 100-tile map.
  - need: Civ6 multi-city scenario — N cities, each with its own workable radius, must not overlap, and the overall objective is the sum of every city's adjacency.
    context: Cities compete for high-value tiles within reach; assigning all the best tiles to one city starves the others. Naive single-city anchor search would converge on the best one and ignore the rest.
    action: >
      Generate `get_anchor_candidates` as combinatorial K-tuples of
      non-overlapping city centers (cap with a beam over the
      highest-coverage tuples), and let `greedy_expand` fan out across
      all chosen centers in one pass picking the globally best marginal
      district at each step. `local_search` may transfer a district
      from one city to another if the swap improves total adjacency.
    outcome: A balanced multi-city plan whose `total_adjacency` beats per-city greedy by avoiding mutual starvation.
  - need: Strategic siting on a square grid — place K depots to maximize coverage minus overlap, subject to terrain constraints.
    context: Same shape as Civ6 adjacency; the only difference is square instead of hex neighbors and an objective that includes a penalty for double-coverage. Without pruning, the search space is too large to enumerate.
    action: >
      Reuse `optimize_placements` with `is_valid` keyed on terrain,
      `score` as `coverage - lambda * overlap` over square neighbors,
      `get_anchor_candidates` as the top-scored cells thinned to a
      minimum mutual distance, and a `local_search` that swaps depots
      pairwise to reduce overlap.
    outcome: A near-optimal depot plan found in O(seconds) without writing a bespoke solver.

integrations:
  - partner: civ6lib
    body: >
      Provides district yield tables, terrain rules, and the adjacency
      bonus rules that the `score` callable consults. Source of truth
      for "what does CAMPUS gain from each neighbor type" — never
      hardcode adjacency constants in the scorer; look them up from
      this library so rule changes propagate.
  - partner: hex-grid-spatial
    body: >
      Provides the hex neighbor / distance / range primitives used by
      `is_valid` (range from city center) and `score` (which tiles are
      adjacent to a candidate). Use its neighbor helpers rather than
      re-deriving offset math — hex parity bugs are silent and corrupt
      adjacency totals.
  - partner: sqlite-map-parser
    body: >
      Loads the `.Civ6Map` file into a tile list with terrain, features,
      resources, and coordinates. Always the first thing the agent
      runs; the parsed tile list is the input to `prune-search-space`.
  - partner: external CP-SAT / ILP solvers (OR-Tools, Gurobi)
    body: >
      Drop in for problems where a proven optimum matters more than
      wall-clock or where the objective is non-decomposable. This
      skill's heuristic and a CP-SAT model can also be paired&#58; use
      the heuristic's best plan as a warm start for the solver to cut
      its branch-and-bound time.

anti_patterns:
  - "Skipping pruning and feeding the raw tile set into scoring or anchor search. Every tile dropped saves exponential downstream work; you cannot recover the speedup later."
  - "Pruning by `is_valid` only. The dominance and isolation filters routinely double the pruning yield; omit them only when the scorer is so cheap that pruning doesn't pay (rare)."
  - "Treating `score(tile)` as a pure function of the tile alone. Adjacency bonuses depend on neighbors, so the scorer must consult the candidate set; treat the score as `f(tile, neighbors_in_candidates)` and re-score when the candidate set changes materially."
  - "Optimizing one metric without considering interactions. Placing district A may change the value of placing district B (adjacency effects, mutual exclusion). Balance intrinsic value with flexibility for the placements that still have to be made."
  - "Running anchor search with a single anchor candidate. The anchor IS the search bias; try several (top-K anchors, or all anchors above a coverage threshold) and keep the best."
  - "Treating the greedy result as final. Local search — swap, relocate, drop-and-replace — typically improves the greedy total by 5-15 percent and costs little once the anchor is fixed."
  - "Forgetting the final validation pass. The pruning step validates *per-tile*; the final configuration must also be validated *as a whole* (no two placements share a tile, the city center count matches the task input, every placement is in range)."
  - "Hardcoding adjacency rule numbers in the scorer instead of looking them up from `civ6lib`. Rules change between Civ6 patches; the lookup keeps the strategy correct without code edits."
  - "Returning a placement plan whose `adjacency_bonuses` sum does not equal `total_adjacency`. The Civ6 task verifier checks this exactly and gives zero points on mismatch — recompute and assert before writing the output JSON."
```
