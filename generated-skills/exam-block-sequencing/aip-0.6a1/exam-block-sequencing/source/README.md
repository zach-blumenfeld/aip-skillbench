# Source material and compilation notes: exam-block-sequencing

## Provenance

Compiled from two curated Agent Skills, copied verbatim into this folder:

- `mip-solver-and-solution-audit/SKILL.md`: picking a solver (PySCIPOpt first), keeping incumbent/bound/gap certificates, extracting the solution, writing metrics with an independent evaluator, and making the reports consistent.
- `ordered-window-sequencing-mip/SKILL.md`: permutation MIPs with ordered local-window variables, prefix/suffix continuity, start masks, and overlap penalties.

The task context came from the exam block sequencing task statement (24 blocks, 24 slots, weights 1/1/10/10/5, four output files) and its data folder: `instance.json`, ordered `pair_counts.csv` and `triplet_counts.csv`, and a README that defines the overlap term as the ordered triplets (a,b,c) and (a,c,d) on two consecutive qualifying three-slot starts. Every loader assumption was tested against those files exactly as shipped. The tests also used transformed copies: relabeled blocks, a non-contiguous `all_slots` list, a virtual block, different front-loading sets and weights, no README, inactive front-loading, and infeasible front-loading.

## Intent

An agent with this skill mounted should turn any instance of this task into four audited files. The objective must follow the instance's own masks, slot order, and overlap definition. The schedule should come from a solver-backed hybrid method under a time limit, and the report must be honest about what was certified.

## Component-kind choices

| Step | Kind | Why |
|---|---|---|
| load-instance | execution | Parsing, validation, slot order, start masks, front-loading feasibility and weight normalization are deterministic rules. |
| overlap-semantics | decision (choice) | The overlap term's definition is written in prose in the data README, and the possible answers can be listed in advance. The source skill stresses that these definitions are not interchangeable. A typed label feeds the scripts; threshold 0.7 because a wrong answer silently optimizes a different objective. |
| solve | execution | Heuristic search plus MIP build and solve: pure computation. Uses the maintained SCIP solver instead of a hand-written exact method. |
| extend-search | decision (noul) | Whether another longer pass is worth it is a cost/benefit judgment. It weighs convergence signals (agreement between workers, how late the last improvement came, whether the MIP beat the heuristic) against the caller's time budget, which may be soft. Threshold 0.5. |
| by-extend | router | Branches on that noul. |
| refine | execution | Same script as solve (it detects `solve_summary` in its inputs), with doubled budgets and a seed. It shares state through work_dir files, so the join step never reads a branch-only key. |
| write-outputs | execution | Writing, reloading, auditing, recomputing metrics, and rendering the reports are deterministic. Generating the reports from the data keeps every number consistent with the schedule. |
| review-report | client_task | The agent checks the prose against the task statement (which the scripts never see), fills gaps in the wording, and writes the final summary. |

## Design adaptations (not drops)

- **Linearization.** The source's assignment-linked window variables `window[i,j,k,t]` (and 4-index overlap variables) would need about 600k binaries for 24 blocks, which is not practical for SCIP. The skill uses three pieces instead:
  - assignment variables `y`;
  - ordered arc variables `p` with prefix/suffix continuity (the source's continuity template at pair level);
  - one continuous big-M cost variable per (window, adjacent pair), tight at any optimum.

  The overlap term stays inside the optimized model, as the source requires. Because every window has an adjacent pair, gapped overlap triplets (a,c,d) are linearized through the pair at (s+2, s+3).
- **Hybrid method.** The task allows a solver, a heuristic, or a hybrid. A time-limited SCIP run on this model gives a valid dual bound but rarely improves the incumbent, so the incumbent comes from a parallel annealing and iterated-local-search heuristic. That incumbent warm-starts SCIP. The final schedule is the best one by the pure evaluator; on ties the solver-extracted incumbent wins, as the source prefers. The report says whether SCIP improved on the warm start. The gap is always computed against the best SCIP dual bound, which is valid for any feasible schedule.
- **SCIP tuning.** Fast presolve and fast primal heuristics are set because the default presolve sometimes used the whole 60 s budget without finishing the root LP. An infinite or missing dual bound is replaced by the trivial bound 0 (all counts are non-negative), and the report says so.
- **Solver/evaluator check.** The source raises an AssertionError when the solver objective and the evaluator disagree. Here the check result is recorded in runs.json and printed in the report. Metrics always come from the evaluator.

## Completeness check (source item → where it lives)

mip-solver-and-solution-audit:
- One final solution with consistent files; feasible is not optimal → write-outputs (single best.json, reload, round-trip) and anti_patterns.
- Solver discovery, prefer PySCIPOpt, do not abandon after one failed import, do not use a heuristic only when a solver is required → `requires.packages: pyscipopt`, lazy import with error capture in `build_and_solve_mip`, anti_patterns.
- Minimal PySCIPOpt pattern (time limit, getNSols, getBestSol, objective, getDualbound, getGap, getSolVal rather than var.getVal) → `seqcore.build_and_solve_mip`, anti_patterns.
- Record solver, status, time limit, incumbent, bound, gap, certification; manual gap formula; prefer solver gap → solve_summary, runs.json, formulation.md, report.md (both gaps reported).
- Extraction at > 0.5, validating hard rules from the artifact, finite numerics → extraction checks, `check_feasible`, bound/gap sanitizing.
- Independent pure evaluator, comparison with solver objective → `seqcore.evaluate`, `solver_objective_matches_evaluator`.
- Evaluator mirrors official semantics (ordered keys, masks, successor relation, exact overlap, missing rows) → `load_instance`, `build_terms`, `evaluate`, references/objective-semantics.md.
- Never write metrics before reloading the artifact; round-trip template → write_outputs.
- Post-processing disclosure; prefer the solver incumbent → `best_source`, tie preference, "SCIP kept/improved" line.
- Formulation contents and the exact wording list (minimize, each item exactly once, each slot one item, no duplicates/missing, pair, n-gram and overlap terms, front-loading even when inactive, approach and whether time-limited) → formulation.md generator, review template, references.
- Output consistency workflow 1–9 → solve then write-outputs, in order.
- Common mistakes → anti_patterns plus references/objective-semantics.md.

ordered-window-sequencing-mip:
- Modeling workflow 1–8 (positions, items, variable choice, hard constraints, auxiliaries, tight linking, named components, extraction and audit) → `build_and_solve_mip`, formulation.md sections.
- Preserve ordered tuple data; never sort or symmetrize; both (i,j) and (j,i) present does not mean summing them; decide what missing rows mean → `_read_counts` (ordered keys, missing = 0), anti_patterns, references.
- One small evaluator expression per component over eligible starts → `evaluate`.
- Assignment-linked windows with McCormick linking → adapted as above (arc variables plus big-M window costs); the lower-bound linking is the big-M constraint.
- Direct ordered-window model and prefix/suffix continuity; cyclic wraparound only if cyclic → pair continuity constraints; no wraparound (anti_patterns).
- No repeated items in windows → `p` only for i ≠ j; window cost terms exclude k ∈ {i, j}.
- Overlap penalties stay inside the model; tell the four "three in four" definitions apart → overlap-semantics decision, `OVERLAP_RULES`.
- Active-pattern overlap rule (primitive pattern, active-start set, membership, cost) → `starts["three_in_four"]` = consecutive qualifying triple starts; cost from the chosen rule.
- Start masks kept separate from weights; no extra boundary windows; successor map from declared positions, not label arithmetic → `load_instance` (`all_slots`/`slots` honored; tested with labels 10..240).
- Objective semantics audit questions → references/objective-semantics.md, formulation.md problem section.
- Common mistakes → anti_patterns.

## Deliberate-drop log

- Generic examples from other domains (routes, machines, shifts, customer visits) and the "use this pattern for..." lists: background only. The skill targets exam block sequencing, and the description still covers similar permutation problems.
- The illustrative code snippets in both sources (wrong-shortcut example, generic templates): replaced by working scripts that implement the correct version.
- "If the task explicitly allows substitution, heuristics are fine": covered by the hybrid design. The task statement allows heuristic or hybrid methods, and the solver is still used for the bound.
