---
name: exam-block-sequencing-mip
description: "Sequence exam blocks (or jobs, visits, tasks) into ordered slots as a permutation that minimizes weighted ordered pair, triplet and overlapping three-in-four burdens, with front-loading of large blocks into early slots. Builds and solves a mixed-integer program with PySCIPOpt (SCIP) (warm-started by iterated local search), audits the written schedule with an independent evaluator, and writes schedule.csv, metrics.json, formulation.md and report.md with honest solver status, bound and gap. Use for final-exam block sequencing, back-to-back, same-day triple or 24-hour triple minimization, or any ordered-window sequencing MIP task that needs a formulation write-up."
compatibility: "Python >= 3.10 with numpy, pandas, pyscipopt (SCIP); tested with python 3.12, numpy 1.26.4, pandas 2.2.2, pyscipopt 6.1.0. No network, no other tools."
---

# Exam Block Sequencing MIP

## Trigger When

1. A task asks to assign exam blocks to exam slots (one block per slot) to minimize back-to-back, same-day triple, 24-hour or cross-day triple, or "three in four" pressure counts.
2. Inputs look like `/root/data/instance.json` (block list, start-position lists such as `triple_day_start`, `eve_morn_start`, `large_blocks`, `early_slots`) plus ordered `/root/data/pair_counts.csv` and `/root/data/triplet_counts.csv`.
3. Any permutation or sequencing problem whose cost depends on ordered adjacent pairs, sliding triples, or overlapping local windows, and the deliverable needs a MIP formulation, solver status, bound and gap.

## Purpose

Turns the instance files into one audited schedule: it fixes the objective semantics that agents get wrong (ordered tuple keys, declared start masks, the specific overlap rule), finds a strong permutation with a fast batch local search, attempts to prove improvement with an exact-objective SCIP model warm-started from it, recomputes every metric from the schedule file on disk, and renders a formulation and report whose numbers all describe that same final schedule.

## Before you start

Check the runtime: `python3 -c "import numpy, pandas, pyscipopt"`. Name every missing package. If only `pyscipopt` is missing, the solve step still runs (heuristic only) and says so; report that honestly. Run all commands from this skill's folder; `--data` and `--out` default to `/root/data` and `/root/output`.

## Workflow

### 1. Inspect the instance (script)

```bash
python3 scripts/blockseq.py inspect --data /root/data
```

Prints block and slot counts, the slot order used, virtual blocks, front-loading status, every start list mapped to slot labels, the overlap starts, table sparsity, whether tables happen to be symmetric, and the weights and offsets in force. It fails loudly if blocks ≠ slots, a start list names an unknown slot, or there are more large blocks than early slots.

Facts the script already enforces (do not re-implement):
- Slots are taken in the instance's order (`all_slots` if present, else `1..N`); next(s) is the following slot in that list, never `label+1` arithmetic on non-contiguous labels.
- Pair and triplet keys are ordered in schedule order; never sorted or symmetrized, even if `inspect` reports the tables symmetric. Missing rows count as 0; self-pairs are never scored.
- `virtual_blocks` are scheduled exactly like normal blocks (added to the block set if absent).
- Large blocks may only occupy `early_slots`. If either list is empty the constraint is inactive, but it is still stated in the formulation.

### 2. Fix the objective semantics (decision)

Read `/root/data/README.md` and the task instruction, then answer in one pass:

```yaml
overlap_definition:
  type: choice
  instructions: For four consecutive assigned blocks a,b,c,d (slots s..s+3), which ordered triplets does the overlapping four-slot / three-in-four term add?
  criteria:
    abc_acd: The data README says the term uses (a,b,c) and (a,c,d). Default; matches the shipped README.
    abd_acd: The source names (a,b,d) and (a,c,d), i.e. the triples not already counted as consecutive windows.
    custom: Some other ordered offset set within the four slots, written as offsets from s.
    none: The task has no overlap or three-in-four term.
overlap_starts_rule:
  type: noul
  instructions: Does the overlap term apply exactly when s and next(s) both start a qualifying three-slot window (s in triple_day_start or triple_24_start, and the same for next(s))?
  criteria:
    true: The source says the term applies when two qualifying three-slot windows start in consecutive slots, or says nothing more specific.
    false: The source restricts or extends the starts differently (e.g. same-day only, or an explicit start list).
tables_explicitly_unordered:
  type: noul
  instructions: Does the source explicitly state the pair and triplet tables are unordered or must be symmetrized?
  criteria:
    true: Explicit wording such as "unordered", "symmetric, sum both directions", or "sort keys".
    false: Rows keyed (i,j) or (i,j,k) with no such statement, or a statement that they are ordered. Default.
missing_rows_zero:
  type: noul
  instructions: Do missing pair and triplet rows mean zero co-enrollment?
  criteria:
    true: Sparse count tables, or no statement otherwise. Default.
    false: The source says a missing row makes that adjacency invalid or forbidden.
```

A wrong `true` on `tables_explicitly_unordered` or a wrong overlap choice silently optimizes a different objective, so reconsider any close call toward the default. Act on the answers:

| Answer | Action |
|---|---|
| `abc_acd` | default `--overlap-offsets "0,1,2;0,2,3"` |
| `abd_acd` | `--overlap-offsets "0,1,3;0,2,3"` |
| `custom` | `--overlap-offsets "0,i,j;..."` (MIP supports `(0,1,k)` and `(0,k,k+1)`; otherwise solve falls back to heuristic-only, see step 3) |
| `none` | `--w-overlap 0` |
| `overlap_starts_rule = false`, `tables_explicitly_unordered = true`, or `missing_rows_zero = false` | Edit `build_terms` or `load_tables` in `scripts/blockseq.py` to match the source (client task), re-run `inspect`, and state the deviation in report.md. Read `references/modeling-notes.md` first. |

Weights: map the instruction's weights onto flags, defaults shown: evening-to-morning back-to-back `--w-eve-morn 1`, other back-to-back `--w-other-b2b 1`, same-day triple `--w-same-day 10`, cross-day or 24-hour triple `--w-cross-day 10`, overlapping four-slot pressure `--w-overlap 5`. Pass every flag that differs, and pass the same weight and offset flags to `solve`, `audit` and `report` alike.

### 3. Solve (script)

```bash
python3 scripts/blockseq.py solve --data /root/data --out /root/output [weight and offset flags]
```

What it does: iterated local search over feasible permutations (`--heur-seconds`, default 120; seed `--seed 0`) → SCIP MIP with the exact objective, warm-started from that schedule (`--time-limit`, default 180 s) → extracts the incumbent, checks feasibility, asserts the solver objective equals the independent evaluator, writes `/root/output/schedule.csv` (columns `slot,block`, one row per slot in slot order) and `/root/output/solve_info.json` (method, status, incumbent, bound, gap, time limit, warm-start acceptance, heuristic stats). Expect ~5–6 minutes at 24 blocks with defaults.

Branches:
- MIP finished → `method: mip`; status `optimal` only when proven (small instances), otherwise `timelimit` with a large gap (the big-M bound is weak). That is expected; it is still the solver incumbent.
- `pyscipopt` missing or offsets unsupported → warning on stderr, `method: heuristic`, no bound or gap. If the task allows heuristics (the exam task does: "a solver, a heuristic method, or hybrid"), keep it and say so in the report. If the task requires a solver-based integer program, do not submit heuristic-only output: get `pyscipopt` importing (or extend the model) and re-run.
- Tight runtime budget → `--heur-seconds 45 --time-limit 60`. At 24 blocks SCIP may then stop before its root LP finishes: bound 0, gap reported as infinite. The incumbent is still valid; report it as unproven. More budget → raise `--heur-seconds` first; the local search finds the good schedules, SCIP mostly certifies.
- `--time-limit 0` skips the MIP deliberately (heuristic only).

Do not replace the model with a full triple-window formulation at this size; it does not get past presolve in minutes (see `references/modeling-notes.md`).

### 4. Audit the written schedule (script)

```bash
python3 scripts/blockseq.py audit --data /root/data --out /root/output [same flags]
```

Reloads `/root/output/schedule.csv` from disk, checks each block exactly once, each slot exactly one block, row count, and large blocks only in early slots; recomputes all five counts and the weighted objective with a pure evaluator; writes `/root/output/metrics.json` with keys `objective, eve_morn_b2b_count, other_b2b_count, same_day_triple_count, cross_day_triple_count, z_three_in_four_count`; round-trips it; and checks it against `/root/output/solve_info.json`. Exit 1 with a JSON error list means the schedule is infeasible or inconsistent: fix and re-run `solve`, never hand-edit `/root/output/metrics.json`. If you change `/root/output/schedule.csv` after `solve` for any reason, rerun `audit` and disclose the post-processing; the solver certificate no longer applies.

### 5. Write formulation.md and report.md (script)

```bash
python3 scripts/blockseq.py report --data /root/data --out /root/output [same flags]
```

Renders `assets/formulation.md.tmpl` and `assets/report.md.tmpl` from `/root/output/solve_info.json`, `/root/output/metrics.json` and `/root/output/schedule.csv`: the word "minimize", decision variables, "each block exactly once" / "each slot exactly one block", front-loading, the linearization of each component, solver, time limit, status, incumbent, bound, gap, certification wording, score breakdown, feasibility check and the schedule table.

### 6. Review the deliverables (client task)

Read both rendered files and the audit output. Add a short note to report.md (and formulation.md if the model changed) for anything the templates cannot know: a semantics override from step 2, a non-default weight, a heuristic-only fallback and why, or any post-processing. Never call the result optimal unless the status is `optimal` or the gap is 0. Confirm `/root/output/` holds schedule.csv, metrics.json, formulation.md and report.md (the extra `/root/output/solve_info.json` is harmless).

## Gotchas

- The pair table on the shipped instance is symmetric; that does not license summing both directions for one window. One window = one ordered key.
- The overlap term is not "all triples inside a four-slot span". On the shipped README it is `T[a,b,c] + T[a,c,d]` for each overlap start.
- Start lists are masks: a back-to-back count only includes starts in its list; do not add windows across boundaries the instance did not list.
- Reported metrics come from the file on disk, not from solver expressions or an in-memory schedule.
- Time-limited SCIP status means "feasible incumbent", not optimal; the relative gap can exceed 100% with this compact model.
