# Authoring notes — map-optimization-strategy (AIP conversion)

## Source

`original-SKILL.md` is the curated Agent Skill that ships with the
`civ6-adjacency-optimizer` SkillsBench task. This AIP version preserves the
methodology and content verbatim where possible, restructured into the
`procedure.schema.json` execution graph.

## Schema choice

`procedure.schema.json` — the source is a multi-phase strategy/algorithm
(prune → score → anchor-search), which is the textbook shape for the
Procedure schema. No new schema needed.

## Why this skill is a thin script + thick prose

The source is intentionally a **strategy** skill, not an implementation. Its
description states it applies to "any problem where you must place items on a
grid to maximize an objective while respecting placement constraints." So the
backing script (`scripts/optimize.py`) is a generic algorithm shell that takes
problem-specific functions (validity, scoring, neighbor lookup) as inputs.

The agent still needs to author those functions from the domain libraries
(`civ6lib`, `hex-grid-spatial`) — this skill provides the search algorithm,
not the game rules.

### What was scripted

`scripts/optimize.py` exposes:

- `prune_candidates` — deterministic filter loop. Drops invalid /
  dominated / isolated tiles given caller-supplied predicates. Scripted
  because the loop structure is fixed; the predicates are pluggable.
- `score_and_rank` — deterministic: score every tile, sort descending.
- `greedy_expand` — deterministic algorithm with a clear loop invariant
  (pick highest marginal-value tile each step). Scripted.
- `local_search` — deterministic swap loop with a convergence condition.
  Scripted.
- `optimize_placements` — wraps the full pipeline.

All five are mechanical loops over caller-supplied scoring/validity
callables — exactly the "fixed if/then/else over structured inputs" case
from the AIP scripting guide.

### What was kept as prose

- `characterize-problem` — judgment-heavy: deciding what "intrinsic value"
  and "domination" mean for a specific objective is interpretive, not
  mechanical.
- `enumerate-anchors` — judgment call which tiles to anchor from; the
  defaults are a starting point, the agent tunes per problem.
- `select-best` — trivial argmax, but bundled with judgment about
  tie-breaking and fall-back when the top solution fails validation.
- `validate-and-finalize` — the validity check itself is scripted
  (delegated to `civ6lib`); deciding what to do on failure is judgment.

## Content classification against the original

Every section of `original-SKILL.md` is mapped into the AIP body or scripts.

| Source section            | AIP destination                                                     | Status |
|---------------------------|---------------------------------------------------------------------|--------|
| Overview paragraph        | `purpose`                                                            | Mapped |
| Why exhaustive search fails | `anti_patterns[0]` (brute force) + `references/algorithm-details.md` | Mapped |
| Phase 1: Prune            | step `prune-search-space` + script + `references/algorithm-details.md` | Mapped |
| Phase 2: Identify high-value spots | step `score-and-rank` + script                              | Mapped |
| Phase 3: Anchor search    | steps `enumerate-anchors`, `anchored-greedy-search`, `local-search-refine`, `select-best` + script | Mapped |
| Algorithm skeleton (Python) | `scripts/optimize.py`                                              | Mapped (concretized) |
| Center-constraint hint    | `modes.center-search` + Civ6 scenario                                | Mapped |
| Key insights              | `anti_patterns` + `purpose` paragraph + `references/algorithm-details.md` | Mapped |
| Common pitfalls           | `anti_patterns`                                                      | Mapped |

Nothing was dropped.

## Additions beyond the source

- `do_not_use_when` — small problems, non-spatial, independent placements.
- `scope_and_approval` — clarifies read/compute-only.
- `modes` — quick / full / center-search.
- `integrations` — explicit pairing with `civ6lib`, `hex-grid-spatial`,
  `sqlite-map-parser`. The source skill ships alongside these in the task
  environment; the AIP version makes the composition explicit so the agent
  knows where to source validity/scoring functions.
- `scenarios` — one Civ6 worked example, one generic facility-siting example.
- `references/algorithm-details.md` — progressive disclosure for deeper
  algorithmic content (combinatorial explosion math, scoring weightings,
  constraint propagation, when to use exhaustive vs heuristic).
- `scripts/optimize.py` — runnable reference implementation of the
  algorithm skeleton that was pseudo-code in the source.

## Name constraint

The frontmatter `name:` MUST remain `map-optimization-strategy` — the
SkillsBench task mounts the skill under that exact folder name.
