# map-optimization-strategy — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill `map-optimization-strategy`
(the `aip-from-curated` track for the `civ6-adjacency-optimizer` task).
The canonical original is preserved verbatim at
`source/ORIGINAL_SKILL.md`. The skill `name` is kept as
`map-optimization-strategy` because the task mounts it under that exact
folder name and the test harness expects that identifier.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md`.
- `source/procedure.schema.json` — the AIP `procedure` schema (v0.3a2)
  the body validates against. Bundled locally so the skill is
  self-contained even though the `$id` points to the canonical URL.
- `scripts/optimize_placements.py` — **new** for the AIP conversion.
  Encodes the three-phase algorithm skeleton from the original SKILL.md
  as a reusable Python function with pluggable domain callables.

## Schema choice

`procedure` schema (reused, not drafted). The original skill is a
three-phase algorithm with explicit ordering, optional refinement, and
a validation step at the end — exactly the procedure-as-execution-graph
the schema models. Steps map cleanly to graph nodes with
`depends_on` edges; the algorithm skeleton becomes the `script` field
on the three execution-phase steps.

## Why a script was added

The original skill is high-level strategy prose with a Python algorithm
skeleton inlined in a code block. Per AIP best practice, anything
expressible as code — and especially anything that encodes ordering
constraints, threshold defaults (`top_k = max(num_placements * 4,
12)`), or iteration loops — belongs in `scripts/`, not in the body.
The skeleton was lifted into `scripts/optimize_placements.py` as a
reusable function. The skill body now points the agent at the script
for the three execution-phase steps and uses prose for the modeling and
validation steps where the domain callables and the output format are
problem-specific.

The script accepts callables for `is_valid`, `score`,
`get_anchor_candidates`, `greedy_expand`, and `local_search` so the
same skeleton drives any item-on-tile problem. For the Civ6 task those
callables are wired against the sibling skills (`civ6lib`,
`hex-grid-spatial`, `sqlite-map-parser`).

## Source-content classification (completeness check)

- Title + opening paragraph ("A systematic approach to solving
  placement optimization problems on spatial maps...") → **Mapped** to
  `purpose` and `description`.
- "Why Exhaustive Search Fails" (combinatorial explosion, O(M^N), the
  50-tile / 5-item / 312M example) → **Mapped** to `purpose` (the
  motivation paragraph cites the same numbers).
- Phase 1 "Prune the Search Space" with the three filters (invalid,
  dominated, isolated) and the 70-90 percent reduction claim →
  **Mapped** to step `prune-search-space` (description carries the
  three filters and the reduction claim) and to the script's pruning
  block.
- Phase 2 "Identify High-Value Spots" with the three scoring
  components (intrinsic, adjacency potential, cluster potential) and
  the priority-tiles concept → **Mapped** to step `score-and-rank-tiles`
  and the script's `Phase 2` block.
- Phase 3 "Anchor Point Search" with anchor selection, greedy
  expansion, constraint validation, local search, and the "anchor IS
  the center" Civ6-specific note → **Mapped** to step
  `anchor-point-search` and the script's `Phase 3` block.
- "Algorithm Skeleton" Python code block → **Mapped** to
  `scripts/optimize_placements.py`. The function structure, the
  `for anchor in ...` loop, the score comparison, and the
  `(greedy → local search → keep best)` ordering all preserved.
- Key Insight 1 "Prune early, prune aggressively" → **Mapped** to the
  `prune-search-space` description and to the first `anti_pattern`.
- Key Insight 2 "High-value tiles cluster" → **Mapped** to
  `score-and-rank-tiles` description (cluster-potential component) and
  to the script's `top_k` default sizing.
- Key Insight 3 "Anchors constrain the search" → **Mapped** to
  `anchor-point-search` description ("the anchor IS the center").
- Key Insight 4 "Greedy + local search is often sufficient" →
  **Mapped** to `anchor-point-search` description (greedy + local
  search ordering) and to the `local_search` callable in the script.
- Key Insight 5 "Constraint propagation" → **Mapped** to the
  `validate-and-emit` step description (the configuration-level
  validation pass) and implicitly to `greedy_expand` updating its own
  candidate set as it places.
- Common Pitfall "Ignoring interactions" → **Mapped** to an explicit
  `anti_pattern`.
- Common Pitfall "Over-optimizing one metric" → **Mapped** to an
  explicit `anti_pattern`.
- Common Pitfall "Forgetting to validate" → **Mapped** to the
  `validate-and-emit` step and to an explicit `anti_pattern`.

## Additions beyond the source

Items added that the original did not contain, in service of the task
this AIP variant is bundled for:

- `trigger_when` / `do_not_use_when` — the original had a single
  `description` sentence. Made activation criteria explicit, including
  cases (small enumerable problems, pure assignment, dedicated solver
  already present, non-decomposable objective) where general agent
  reasoning or a different tool is the better fit.
- `integrations` — the task mounts this skill alongside `civ6lib`,
  `hex-grid-spatial`, and `sqlite-map-parser`. Wiring the strategy to
  those siblings is critical to autonomous task solution and the
  original SKILL.md doesn't mention them.
- `scenarios` — three worked applications (Civ6 single-city, Civ6
  multi-city, generic facility siting on a square grid) make the
  abstract strategy concrete and show that the same skeleton handles
  variants the task may surface.
- Task-output-format reminder in `validate-and-emit` and a dedicated
  anti-pattern about the `adjacency_bonuses` sum matching
  `total_adjacency`. The task verifier checks this exactly and the
  original SKILL.md does not flag it.
- The `top_k = max(num_placements * 4, 12)` default in the script.
  The original code uses a `top_k` variable without specifying a value;
  pinned to a concrete default with a documented override rationale.
