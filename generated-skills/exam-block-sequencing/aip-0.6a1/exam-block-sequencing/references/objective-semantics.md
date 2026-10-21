# Objective semantics and audit rules (load when reviewing outputs or changing the model)

Distilled from `source/ordered-window-sequencing-mip` and `source/mip-solver-and-solution-audit`.

## Semantics the scripts implement

- Sequence: one block per slot, slots in the order of `instance.json` (`all_slots`/`slots` if present,
  else 1..len(all_blocks)). "Next" is the successor in that order, never `label + 1` arithmetic on
  non-contiguous labels.
- Pair and triplet tables are ordered. Window key = blocks in schedule order:
  `(b(s), b(next s))`, `(b(s), b(s+1), b(s+2))`. Never sort, symmetrize, add the reverse pair, or sum
  all permutations, even though the table holds both (i,j) and (j,i) — that is just a complete
  ordered table. Missing rows count 0 (sparse tables).
- Each component reads only its own start mask: `eve_morn_start`, `other_b2b_start` (pairs),
  `triple_day_start`, `triple_24_start` (triples). No extra boundary windows, no cyclic wraparound.
- Overlap / "three in four" / z term: primitive pattern = a qualifying three-slot window (a start in
  `triple_day_start ∪ triple_24_start`). Active overlap = two such windows starting at consecutive
  slots s, next(s). Cost = the ordered triplets named by the data README (default
  `(a,b,c)` and `(a,c,d)` for blocks a,b,c,d in slots s..s+3). These definitions differ and are not
  interchangeable: all unordered triples in a 4-span; ordered triples with span ≤ 4; pairs of
  adjacent active windows; explicit source-formulation variables.
- Front-loading: every block in `large_blocks` must sit in a slot of `early_slots`. Virtual blocks
  are ordinary blocks.

## Audit discipline

- One final solution: schedule.csv, metrics.json, formulation.md, report.md all describe the same
  schedule. Metrics are recomputed from the reloaded schedule.csv by the pure evaluator, never from
  solver expressions.
- Feasible is not optimal. Claim "optimal" only when the gap is closed. Time limit / node limit
  statuses mean "incumbent". Gap = (incumbent − bound) / max(1, |incumbent|); SCIP's own gap is also
  reported. The SCIP dual bound is valid for any feasible schedule of the same model, so the gap of a
  post-processed or heuristic final schedule is still computed against it — but say which run
  produced the final schedule.
- If post-processing changed the solver's schedule, disclose it and recompute everything.
- The formulation must say "minimize", "each block assigned exactly once", "each slot exactly one
  block", "no duplicates or missing assignments", name adjacent-pair, three-position, and overlap
  terms, the front-loading constraint (even when inactive), solver, time limit, status, incumbent,
  bound, gap, and whether the method is exact, time-limited, or heuristic.

## Common mistakes to check for in the written files

- Claiming optimality after a time-limited run.
- Objective in report differs from metrics.json, or metrics.json differs from a recompute of schedule.csv.
- Overlap term described as "all triples in a four-slot window".
- Missing solver status, bound, gap, or time limit.
- Formulation that only says "best" or "lowest" without "minimize".
