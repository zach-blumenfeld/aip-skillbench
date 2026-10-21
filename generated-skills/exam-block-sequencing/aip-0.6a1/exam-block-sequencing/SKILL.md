---
name: exam-block-sequencing
description: Sequence exam blocks into ordered final-exam slots by minimizing weighted back-to-back, same-day/24-hour triple, and overlapping three-in-four pressure from ordered pair/triplet co-enrollment counts, with large-block front-loading. Hybrid annealing heuristic plus a SCIP (PySCIPOpt) ordered-window MIP with time limit, bound, and gap; writes schedule.csv, metrics.json, formulation.md, report.md from one audited schedule. Use for exam block sequencing, permutation MIPs with sliding-window costs, or registrar final-exam slot assignment.
metadata:
  aip-version: "0.6a1"
---

# AIP runtime — format 0.6a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the one JSON object a run carries. Each step declares the keys it reads as `inputs`; `execution` and `client_task` steps declare the keys they add as `outputs`, and a `decision` adds one key per question.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the procedure's result.

## Execution

The state starts as the start step's `inputs` and flows along `inputs_to`; each step adds its outputs to it. Every key is produced by exactly one step, so keys accumulate and nothing is overwritten. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. A step sees only those keys: give it its declared `inputs` and nothing else from the state. You have the final say at every step.

- **`execution`**: before the first one, check that this machine has everything `requires` names (the interpreter at its minimum version, the packages, the tools); if anything is missing, stop and name all of it. Run `script` from its folder, launched with the step's `command` when it has one and `python <script>` otherwise, with one JSON object on stdin, `{"state": <the step's inputs>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout holding exactly the step's `outputs`; add them to the state. A non-zero exit, or output missing a declared key, fails the step: stop there and report it rather than doing the step by hand.
- **`decision`**: answer each question from the step's inputs, and from the run so far only when the step sets `history: true`. Each answer collapses to one value under its question name and is added to the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the step's inputs, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the step's `outputs`; add them to the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. Those keys are the procedure's result.

```yaml
purpose: >
  Assign already-formed exam blocks to ordered final-exam slots (a permutation) to minimize the
  weighted student burden from back-to-back pairs, same-day and 24-hour triples, and the
  overlapping four-slot ("three in four") pressure term, honoring front-loading of large blocks.
  Scripts load the instance, build an ordered-window objective, find an incumbent with a parallel
  annealing + iterated-local-search heuristic, solve a compact MIP with SCIP warm-started from it
  (time-limited, with bound and gap), and write schedule.csv, metrics.json, formulation.md, and
  report.md from one audited schedule re-read from disk.

trigger_when:
  - A task asks to sequence exam blocks into exam slots using pair_counts / triplet_counts co-enrollment tables.
  - A registrar or scheduling task gives instance.json with eve_morn_start, other_b2b_start, triple_day_start, triple_24_start, large_blocks, early_slots.
  - A permutation or sequencing problem scores adjacent pairs, sliding triples, and overlapping windows and asks for a MIP formulation, solver status, bound, gap, and recomputed metrics.

do_not_use_when:
  - Exams still need to be grouped into blocks (conflict-free block assignment), not sequenced.
  - The slots are not a single ordered sequence, or several blocks may share a slot.

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - pyscipopt

steps:
  - name: load-instance
    kind: execution
    description: >
      Load instance.json (source of truth for blocks, slot order, start masks, large blocks, early
      slots), the ordered pair and triplet tables, and the data README; normalize the objective
      weights; fail fast on an infeasible front-loading rule. Slot order is instance.json's slot
      list if present, else 1..len(all_blocks).
    inputs:
      - name: data_dir
        type: string
        description: Folder holding instance.json, pair_counts.csv, triplet_counts.csv, README.md (e.g. /root/data).
      - name: output_dir
        type: string
        description: Folder the four deliverables go to (e.g. /root/output); created if missing.
      - name: work_dir
        type: string
        description: Scratch folder for best.json and runs.json, outside output_dir (e.g. /root/work).
      - name: weights
        type: object
        description: >
          Objective weights from the task statement, keys eve_morn_b2b, other_b2b, same_day_triple,
          cross_day_triple, three_in_four (e.g. 1, 1, 10, 10, 5).
      - name: heuristic_seconds
        type: integer
        description: Wall-clock seconds for the heuristic phase of `solve` (default 120; refine doubles it).
      - name: mip_seconds
        type: integer
        description: SCIP time limit for `solve` (default 180; refine doubles it). Keep heuristic + MIP under ~25 min.
      - name: time_budget_seconds
        type: integer
        description: Total wall-clock seconds the caller can spend on solving; decides whether refine is affordable.
    script: scripts/load_instance.py
    outputs:
      - name: instance_summary
        type: object
        description: Block/slot counts, slot order, start-slot masks per component, large/early/virtual lists, loader warnings.
      - name: overlap_text
        type: string
        description: The data README verbatim, which defines the overlap term.
      - name: objective_weights
        type: object
        description: Weights normalized to the five canonical component keys.
    timeout: 120
    inputs_to: overlap-semantics

  - name: overlap-semantics
    kind: decision
    description: >
      Fix the exact definition of the overlapping four-slot pressure term from the data README
      before anything is optimized; the definitions below are not interchangeable.
    inputs:
      - name: overlap_text
        type: string
    questions:
      overlap_rule:
        type: choice
        instructions: >
          For four consecutive assigned blocks a,b,c,d in slots s..s+3, where s and next(s) both
          start qualifying three-slot windows, which ordered triplet counts does the text say the
          overlap / three-in-four / z term charges? Go by the explicit triplets named; if the text
          names (a,b,c) and (a,c,d), that is abc_and_acd even if it also says what the term is not.
          If no README text defines it, answer abc_and_acd.
        criteria:
          abc_and_acd: The text names the ordered triplets (a,b,c) and (a,c,d), or gives no definition.
          acd_only: The text says only the gapped triplet (a,c,d) is charged.
          abd_and_acd: The text names (a,b,d) and (a,c,d), the two triplets that skip one slot.
          all_ordered_triples_in_four: The text explicitly says to charge every ordered triple inside the four-slot span.
    thresholds:
      overlap_rule: 0.7
    inputs_to: solve

  - name: solve
    kind: execution
    description: >
      Heuristic incumbent (parallel multi-restart annealing with feasibility-preserving swap and
      insertion moves, swap/insertion descent, exact 6-slot window re-permutation, iterated local
      search), then the compact MIP in SCIP warm-started from it under a time limit: y[i,s]
      assignment, p[i,j,s] ordered arcs linked by prefix/suffix continuity, big-M triple-window costs.
      Keeps the best schedule by the pure evaluator in work_dir/best.json and logs status, incumbent,
      bound, and gap of every run in work_dir/runs.json.
    inputs:
      - name: data_dir
        type: string
      - name: work_dir
        type: string
      - name: objective_weights
        type: object
      - name: overlap_rule
        type: string
      - name: heuristic_seconds
        type: integer
      - name: mip_seconds
        type: integer
    script: scripts/solve.py
    outputs:
      - name: solve_summary
        type: object
        description: >
          best_objective, best_source, heuristic worker bests and agreement, last-improvement
          fraction, MIP status/incumbent/bound, absolute and relative gap, elapsed seconds.
    timeout: 3600
    inputs_to: extend-search

  - name: extend-search
    kind: decision
    description: Decide whether a second, longer search is worth the remaining time.
    inputs:
      - name: solve_summary
        type: object
      - name: time_budget_seconds
        type: integer
    questions:
      extend_search:
        type: noul
        instructions: >
          Should the search be rerun with doubled budgets (seeded from the current best)? Refine
          costs about 2 x (heuristic_seconds_budget + mip_seconds_budget) plus model build time.
        criteria:
          true: >
            The search looks unconverged — fewer than half of heuristic_worker_best_costs equal
            best_objective, or heuristic_last_improvement_fraction is above 0.6, or the MIP found a
            better incumbent than the heuristic — and time_budget_seconds minus elapsed_seconds
            exceeds that refine cost.
          false: >
            The gap is closed, most workers agree on best_objective with early last improvement, or
            the remaining budget cannot cover the refine cost.
    thresholds:
      extend_search: 0.5
    inputs_to: by-extend

  - name: by-extend
    kind: router
    description: Unconverged searches with budget left get a refine pass; others go straight to the outputs.
    branch_on: extend_search
    branches:
      "true": refine
      "false": write-outputs

  - name: refine
    kind: execution
    description: >
      Same hybrid search and MIP with doubled budgets, new seeds, and the stored best as a seed;
      replaces work_dir/best.json only if the evaluator objective improves and appends its run
      (and its possibly tighter bound) to runs.json.
    inputs:
      - name: data_dir
        type: string
      - name: work_dir
        type: string
      - name: objective_weights
        type: object
      - name: overlap_rule
        type: string
      - name: heuristic_seconds
        type: integer
      - name: mip_seconds
        type: integer
      - name: solve_summary
        type: object
    script: scripts/solve.py
    outputs:
      - name: refine_summary
        type: object
        description: Same fields as solve_summary for the refine pass, with best_objective over both passes.
    timeout: 7200
    inputs_to: write-outputs

  - name: write-outputs
    kind: execution
    description: >
      Write schedule.csv (columns slot,block; one row per slot in slot order) from work_dir/best.json,
      re-load it from disk, audit the hard rules, recompute every metric with the pure evaluator,
      write metrics.json (objective, eve_morn_b2b_count, other_b2b_count, same_day_triple_count,
      cross_day_triple_count, z_three_in_four_count) and round-trip check it, then write
      formulation.md and report.md from that same schedule and the run log. Fails rather than
      writing inconsistent files.
    inputs:
      - name: data_dir
        type: string
      - name: output_dir
        type: string
      - name: work_dir
        type: string
      - name: objective_weights
        type: object
      - name: overlap_rule
        type: string
    script: scripts/write_outputs.py
    outputs:
      - name: metrics
        type: object
        description: The metrics.json content, recomputed from the written schedule.csv.
      - name: feasibility
        type: object
        description: Hard-rule audit of the written schedule (each slot once, each block once, front-loading).
      - name: output_files
        type: list[*]
        description: Paths of schedule.csv, metrics.json, formulation.md, report.md.
    timeout: 300
    inputs_to: review-report

  - name: review-report
    kind: client_task
    description: >
      Read the written report and formulation against the metrics and the task statement; fill
      prose gaps only, never change the schedule or a number.
    inputs:
      - name: metrics
        type: object
      - name: feasibility
        type: object
      - name: output_files
        type: list[*]
      - name: overlap_rule
        type: string
      - name: instance_summary
        type: object
    template: assets/review.md
    references:
      - path: references/objective-semantics.md
        description: Ordered-tuple, start-mask, overlap, and certificate rules plus the wording a formulation must contain. Load when a file looks incomplete or a number looks inconsistent.
    outputs:
      - name: review_summary
        type: string
        description: Final objective, breakdown, feasibility, certificate, and any edits or concerns.
    inputs_to: end

  - name: end
    kind: end
    description: The audited metrics and feasibility of the written schedule, with the reviewer's summary.
    inputs:
      - name: metrics
        type: object
      - name: feasibility
        type: object
      - name: review_summary
        type: string

anti_patterns:
  - Sorting, symmetrizing, or summing both directions of pair or triplet keys; the tables are ordered and complete, not symmetric.
  - Computing the overlap term as all triples (or all combinations) inside a four-slot window instead of the README's named ordered triplets on consecutive qualifying starts.
  - Assuming slot labels are contiguous zero-based indices, adding cyclic wraparound, or scoring windows outside each component's start mask.
  - Dropping the triple or overlap terms from the optimized model to make it smaller and adding them back afterwards.
  - Claiming optimality after a time-limited SCIP run; feasible is not optimal unless the gap is closed.
  - Writing metrics from solver expressions or an in-memory schedule instead of re-reading schedule.csv, or mixing the solver objective of one incumbent with a different submitted schedule.
  - Abandoning an installed solver after one import fails, or submitting a pure heuristic when the task requires a solver-based integer program.
  - Calling unsupported PySCIPOpt methods such as var.getVal(); use model.getSolVal(sol, var). Letting SCIP print to stdout (hideOutput) breaks the step's JSON contract.
  - Rounding non-integral binaries or accepting an extraction with an empty or doubly filled slot instead of fixing the model.
  - Hand-editing schedule.csv or metrics.json after the scripts write them.
```
