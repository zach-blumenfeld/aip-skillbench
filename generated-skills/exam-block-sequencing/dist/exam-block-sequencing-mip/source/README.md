# Provenance and design log: exam-block-sequencing-mip

## Sources (copied verbatim)

| File | Origin | Role |
|---|---|---|
| `mip-solver-and-solution-audit/SKILL.md` | curated skill (inputs/skills) | solver discovery, PySCIPOpt pattern, certificate reporting, extraction/audit discipline, formulation write-up rules |
| `ordered-window-sequencing-mip/SKILL.md` | curated skill (inputs/skills) | ordered tuple semantics, window/overlap linearizations, start masks, successor map, objective-semantics audit |
| `task-instruction.md` | the task statement the downstream agent receives | weights, hard rules (permutation, front-loading, virtual blocks, slot order), the four output files and their required content |
| `task-data-README.md` | `/root/data/README.md` of the task container | data contract: ordered tables, overlap = (a,b,c)+(a,c,d) when two qualifying triple windows start in consecutive slots |

The two curated skills describe one workflow (build an ordered-window sequencing MIP, then solve
and audit it); they were compiled into one skill specialised to exam block sequencing while keeping
the generic rules.

## Build and test notes

- Container: python 3.12-slim with numpy 1.26.4, pandas 2.2.2, scipy 1.13.1, pyscipopt 6.1.0. The
  script uses only numpy, pandas, pyscipopt (stdlib otherwise). Tested in a venv with those pins.
- Real instance (24 blocks, 18 large, 21 early slots): independent iterated-local-search runs reach
  3943 on most seeds (others 3954-3968); SCIP accepts the warm start and stops at the time limit
  with bound ~1708. Metrics were cross-checked by a hand-written evaluator straight from the README
  definitions.
- Synthetic variants (string labels + virtual block + non-contiguous slot labels; full random
  asymmetric tables with no front-loading and the alternative (a,b,d)+(a,c,d) overlap) were solved
  to proven optimality by SCIP and matched exhaustive enumeration exactly.
- Rejected design: a full length-3 ordered-window model (~281k columns at n=24) spent 226 s in
  presolve and its root LP did not finish in 300 s. Simulated annealing in pure Python was too slow
  to converge (results 3977-4074); replaced by numpy batch neighbourhood evaluation.

## Component kinds

| Component | Kind | Why |
|---|---|---|
| Load + validate instance, slot order, start masks, virtual blocks, front-loading lists (`inspect`) | script | deterministic parsing and rule checks over structured files |
| Objective semantics: overlap definition, overlap start rule, ordered vs unordered tables, missing rows | decision (choice + 3 nouls) | needs reading prose (data README, instruction) but the answer space is fixed and each answer maps to a script flag or a defined edit |
| Weights from the instruction → flags | part of the decision step (direct mapping table) | numbers stated in prose; mapping is a lookup, no judgment beyond reading |
| Heuristic warm start, MIP build/solve, extraction, feasibility check, solver-vs-evaluator check (`solve`) | script | numeric optimisation with a maintained solver (SCIP) plus deterministic checks |
| Reload schedule from disk, recompute metrics, round trip, consistency with solve_info (`audit`) | script | pure evaluator; must be deterministic |
| formulation.md / report.md (`report`) | script (template rendering) | content is fixed structure filled with computed numbers; scripting keeps every number tied to the same final schedule |
| Final review / deviation notes | client task | only the agent knows about overrides, fallbacks or post-processing that happened in its run |
| Editing `build_terms`/`load_tables` when the semantics decision departs from the defaults | client task | code generation for a case the flags cannot express |

## Completeness check (source → skill location)

mip-solver-and-solution-audit:
- Core principle (one solution / metrics / report), feasible ≠ optimal → `solve`+`audit`+`report` scripts; Gotchas.
- Solver discovery, prefer PySCIPOpt, don't give up after one missing package → "Before you start"; script imports pyscipopt; fallback branch.
- No pure heuristic when a solver IP is required → step 3 branches.
- Minimal PySCIPOpt pattern, getSolVal not var.getVal, warm start → `solve_mip` in script; references/modeling-notes.md "PySCIPOpt API notes".
- Incumbent/bound/gap/status/time limit recording, no optimality claims without certificate, manual gap formula, prefer solver gap → solve_info.json, report templates, step 6, references.
- Extraction discipline and hard-rule validation from output → `solve_mip` extraction + `check_feasible`; `audit`.
- Independent evaluator, compare with solver objective, metrics from evaluator → `evaluate`, assertion in `cmd_solve`, `audit`.
- Evaluator must mirror official semantics (ordered keys, start masks, successor relation, overlap as defined, missing rows) → script + step 2 decision + Gotchas.
- Reload final artifact before writing metrics; round trip → `audit`.
- Post-processing disclosure → step 4 and step 6.
- Formulation report contents incl. "minimize", exactly-once wording, pair/triple/overlap terms, inactive eligibility constraints, method/certification → assets/formulation.md.tmpl.
- Output consistency workflow (9 steps) → workflow steps 3-6.
- Common mistakes list → covered by the above items and Gotchas.

ordered-window-sequencing-mip:
- Modeling workflow (positions, items, variable choice, hard constraints, auxiliaries, tight linking, named components, audit) → script MIP; references "Choosing the sequence representation".
- Ordered tuple data, no sorting/symmetrizing, both directions present ≠ sum both, missing-row decision → step 2 decision, Gotchas, script.
- Assignment-linked window linearization, direct ordered-window model, prefix/suffix continuity, cyclic caveat → references/modeling-notes.md.
- Overlap penalties, keep high-order terms in the model, distinguish overlap definitions, active-pattern rule and wrong shortcut → script (overlap in MIP objective), step 2 decision, references, Gotchas.
- Start masks and boundary rules, successor map from ordered positions → script (`load_instance`, `build_terms`), step 1 facts, Gotchas.
- Objective-semantics audit questions → step 1 (`inspect`) + step 2 decision.
- Common mistakes (no-repetition, lower-bound linking, cyclic in metrics, dropping terms) → script (no a==b vars, linking constraints), references.

Task instruction and data README: weights, permutation, front-loading, virtual blocks, slot order,
overlap definition, output files and contents → script defaults, step 2 table, templates.

## Deliberate drops

- Generic domain examples (routes, shift plans, machine positions, customer groups) in the source
  intros: background only; the trigger list keeps "jobs, visits, tasks" and the generic
  ordered-window case.
- Generic Python skeletons (`evaluate_output`, `load_final_output`, `weighted_sum`, the
  `component += weight_table.get(key, 0)` loop): replaced by working implementations in
  `scripts/blockseq.py`, not restated as prose.
- "Arc variables for predecessor-successor relationships": kept as a one-line option in the
  reference; not implemented because the adjacent-pair flow variables y already play that role.

## Functional test log (done in the authoring session, no fresh agents spawned)

Walked the skill from this folder with the body's launch commands on a fresh copy of the real
task data and on synthetic variants:

- Real data, defaults: `inspect` → decision answers abc_acd / true / false / true, default weights →
  `solve` (ILS 3943, SCIP timelimit, incumbent 3943, bound 1708.29, warm start accepted, ~5.5 min
  on a loaded laptop) → `audit` (feasible, counts 733/1970/30/24/140, objective 3943, matches
  solve_info) → `report` → review: no deviations to add.
- Tight budget (`--heur-seconds 45 --time-limit 60`): incumbent 3972, SCIP returned bound 0 and gap
  1e+20; report now renders that as "infinite". Longer heuristic time is what improves the schedule.
- `abd_acd` offsets, `--w-overlap 0`, unsupported offsets (heuristic fallback), missing pyscipopt
  (heuristic fallback), `--time-limit 0`, infeasible schedules (duplicate block, large block in a
  late slot → audit exit 1), and an edited `build_terms` (audit flags the solve_info mismatch) were
  each exercised once.
