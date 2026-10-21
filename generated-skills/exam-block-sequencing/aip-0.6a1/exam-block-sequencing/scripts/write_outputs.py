"""Step write-outputs: write schedule.csv, re-load it from disk, audit it, and write metrics,
formulation, and report from that reloaded artifact only."""
import csv
import json
import os

import seqcore as sc

RULE_TEXT = {
    "abc_and_acd": "count(a,b,c) + count(a,c,d)",
    "acd_only": "count(a,c,d)",
    "abd_and_acd": "count(a,b,d) + count(a,c,d)",
    "all_ordered_triples_in_four": "count(a,b,c) + count(a,b,d) + count(a,c,d) + count(b,c,d)",
}


def load_schedule(path, inst):
    """Parse the exact submitted CSV back into perm[pos] = block index."""
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    pos_of = {s: i for i, s in enumerate(inst["slots"])}
    perm = [None] * inst["n"]
    issues = []
    for r in rows:
        s, b = sc._norm_label(r.get("slot", "")), sc._norm_label(r.get("block", ""))
        if s not in pos_of:
            issues.append(f"unknown slot {s}")
            continue
        if b not in inst["idx"]:
            issues.append(f"unknown block {b}")
            continue
        if perm[pos_of[s]] is not None:
            issues.append(f"slot {s} listed twice")
        perm[pos_of[s]] = inst["idx"][b]
    if len(rows) != inst["n"]:
        issues.append(f"{len(rows)} rows, expected {inst['n']}")
    if any(p is None for p in perm):
        issues.append("some slot has no block")
    return perm, issues


def fmt(x):
    return "n/a" if x is None else (f"{x:.6g}" if isinstance(x, float) else str(x))


def main():
    st = sc.read_stdin()
    data_dir, out_dir, work_dir = st["data_dir"], st["output_dir"], st["work_dir"]
    weights, rule = st["objective_weights"], st["overlap_rule"]
    inst = sc.load_instance(data_dir)
    with open(os.path.join(work_dir, "best.json")) as f:
        best = json.load(f)
    with open(os.path.join(work_dir, "runs.json")) as f:
        runs = json.load(f)
    if best.get("overlap_rule") != rule:
        sc.fail(f"stored best used overlap_rule={best.get('overlap_rule')} but this run uses {rule}")

    os.makedirs(out_dir, exist_ok=True)
    sched_path = os.path.join(out_dir, "schedule.csv")
    with open(sched_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["slot", "block"])
        for slot_raw, b in zip(inst["slot_raw"], best["schedule_blocks"]):
            w.writerow([slot_raw, inst["raw_of"][b]])

    perm, parse_issues = load_schedule(sched_path, inst)
    issues = parse_issues + ([] if parse_issues else sc.check_feasible(perm, inst))
    if issues:
        sc.fail(f"written schedule failed the audit: {issues}")
    metrics = sc.evaluate(perm, inst, weights, rule)
    if abs(metrics["objective"] - best["metrics"]["objective"]) > 1e-6:
        sc.fail("objective recomputed from schedule.csv differs from the stored best")
    met_path = os.path.join(out_dir, "metrics.json")
    with open(met_path, "w") as f:
        json.dump(metrics, f, indent=2)
    with open(met_path) as f:
        if json.load(f) != sc.evaluate(load_schedule(sched_path, inst)[0], inst, weights, rule):
            sc.fail("metrics.json does not round-trip against schedule.csv")

    large_ok = all(inst["allowed"][b][p] for p, b in enumerate(perm))
    feas = {
        "rows": inst["n"], "every_slot_filled_once": True, "every_block_once": True,
        "no_duplicates_or_missing": True,
        "frontload_active": inst["frontload_active"],
        "large_blocks_in_early_slots": large_ok,
        "virtual_blocks_scheduled_as_normal": inst["virtual"],
        "warnings": inst["warnings"],
    }

    mips = [r["mip"] for r in runs if r["mip"].get("available")]
    bounds = [m["best_bound"] for m in mips if m.get("best_bound") is not None]
    best_bound = max(bounds) if bounds else None
    gaps = sc.gap_fields(metrics["objective"], best_bound)
    proven = gaps["absolute_gap"] is not None and gaps["absolute_gap"] <= 1e-6
    certified = "proven optimal (gap closed)" if proven else (
        "feasible incumbent, NOT proven optimal (time-limited solve; gap open)")
    comp_rows = []
    for k, mk in sc.COMPONENTS:
        comp_rows.append(f"| {mk} | {fmt(metrics[mk])} | {fmt(weights[k])} | {fmt(sc.num(metrics[mk] * weights[k]))} |")
    st_ = inst["starts"]
    slots = inst["slots"]

    def sl(key):
        return ", ".join(slots[p] for p in st_[key]) or "(none)"

    run_lines = []
    for r in runs:
        m, h = r["mip"], r["heuristic"]
        run_lines.append(
            f"- **{r['phase']}**: heuristic {h['workers']} worker(s) x {r['heuristic_seconds_budget']} s, "
            f"best {fmt(r['heuristic_objective'])} (worker bests {h['worker_best_costs']}); "
            f"MIP: {m.get('solver', 'unavailable')}, time limit {fmt(m.get('time_limit_seconds'))} s, "
            f"status `{m.get('status')}`, warm start accepted {m.get('warm_start_accepted')}, "
            f"incumbent {fmt(m.get('incumbent_objective'))}, best bound {fmt(m.get('best_bound'))}, "
            f"solver gap {fmt(m.get('solver_gap'))}, nodes {fmt(m.get('nodes'))}, "
            + ("SCIP improved on the warm start"
               if m.get("incumbent_objective") is not None
               and m["incumbent_objective"] < r["heuristic_objective"] - 1e-6
               else "SCIP kept the warm-start incumbent (no improvement found)")
            + (f"; solver objective matches independent evaluator: {m['solver_objective_matches_evaluator']}"
               if "solver_objective_matches_evaluator" in m else "")
            + (f" ({m['bound_note'].lstrip('; ')})" if m.get("bound_note") else "")
            + (f", error: {m['error']}" if m.get("error") else ""))
    mip0 = mips[-1] if mips else {}
    size = (f"{mip0.get('n_binary')} binary variables, {mip0.get('n_continuous')} continuous variables, "
            f"{mip0.get('n_constraints')} constraints") if mip0 else "not built (solver unavailable)"

    formulation = f"""# Exam block sequencing: formulation and solution method

## Problem

Assign {inst['n']} exam blocks to {inst['n']} ordered slots (a permutation) to **minimize** the
weighted student burden from close exam placements. Slot order: {inst['slot_source']}; "next slot"
always means the successor in that order. Pair and triplet count tables are **ordered**; keys are
read in schedule order and never sorted or symmetrized. Missing table rows count as 0.

## Objective (minimization)

minimize  {fmt(weights['eve_morn_b2b'])} * EveMornB2B + {fmt(weights['other_b2b'])} * OtherB2B
        + {fmt(weights['same_day_triple'])} * SameDayTriple + {fmt(weights['cross_day_triple'])} * CrossDayTriple
        + {fmt(weights['three_in_four'])} * ThreeInFour

With b(s) the block in slot s and s+1, s+2, s+3 its successors:

- EveMornB2B = sum over s in eve_morn_start ({sl('eve_morn_b2b')}) of pair(b(s), b(s+1)) — adjacent-pair burden.
- OtherB2B = sum over s in other_b2b_start ({sl('other_b2b')}) of pair(b(s), b(s+1)) — adjacent-pair burden.
- SameDayTriple = sum over s in triple_day_start ({sl('same_day_triple')}) of triplet(b(s), b(s+1), b(s+2)) — three-position burden.
- CrossDayTriple = sum over s in triple_24_start ({sl('cross_day_triple')}) of triplet(b(s), b(s+1), b(s+2)) — three-position (24-hour) burden.
- ThreeInFour (overlapping four-slot pressure, z) = sum over starts s where s and s+1 both begin a
  qualifying three-slot window (s in {sl('three_in_four')}), with (a,b,c,d) = (b(s), ..., b(s+3)),
  of {RULE_TEXT[rule]} (overlap rule `{rule}`). It is not the sum of all triples inside the four-slot span.

## Decision variables

- y[i,s] in {{0,1}}: block i is assigned to slot s (created only where front-loading allows).
- p[i,j,s] in {{0,1}}: block i in slot s and block j in slot s+1 (ordered arc / adjacent-pair window), for every consecutive slot pair, i != j.
- c[i,j,K] >= 0 (continuous): burden charged to the ordered three-position window K = (s1,s2,s3)
  whose adjacent pair holds (i,j). Consecutive windows (s, s+1, s+2) use the pair at (s, s+1);
  gapped overlap windows (s, s+2, s+3) use the pair at (s+2, s+3) and the lone block at s.

Model size: {size}.

## Constraints

- Each block is assigned exactly once: sum_s y[i,s] = 1 for every block i.
- Each slot receives exactly one block: sum_i y[i,s] = 1 for every slot s. Together: no duplicates or missing assignments.
- Front-loading / eligibility: large blocks may only take early slots (y[i,s] fixed to 0 otherwise).
  Status for this instance: {'active' if inst['frontload_active'] else 'inactive (no large blocks or no early slots)'};
  {len(inst['large'])} large blocks, {len(inst['early'])} early slots.
- Virtual blocks ({inst['virtual'] or 'none'}) are assigned exactly like normal blocks.
- Pair linking (prefix/suffix continuity of adjacent windows): sum_j p[i,j,s] = y[i,s] and
  sum_i p[i,j,s] = y[j,s+1] for every consecutive slot pair; this makes p exactly the product y[i,s]*y[j,s+1].

## Linearization of each objective component

- Back-to-back terms (both kinds): linear in the arc variables, weight * pair(i,j) * p[i,j,s].
- Triple terms (same-day and 24-hour) and the overlap term: each ordered window is a product of
  three assignments. For window K with adjacent pair (i,j) at (s, s+1) and third block k at s3:
  c[i,j,K] >= sum_k triplet(i,j,k) * y[k,s3] - M_ij * (1 - p[i,j,s]), with M_ij = max_k triplet(i,j,k)
  (symmetrically for a lone first block). Because exactly one k occupies s3, c equals the ordered
  triplet count when p = 1 and 0 when p = 0 at any optimum (minimization pushes c down).
  Weights of components that share a window (e.g. a triple start that also starts an overlap
  window) are summed on the same c variable. The overlap term stays inside the optimized model.

## Solver and solution approach (hybrid, time-limited)

1. Heuristic incumbent: multi-restart simulated annealing over feasible permutations (swap and
   insertion moves that never move a large block out of the early slots), each restart polished by
   swap/insertion descent and exact re-permutation of every 6-slot window; then iterated local
   search on the best schedules (random-swap kicks and short reheated anneals). Run in parallel
   worker processes with different seeds.
2. Exact MIP above, built in PySCIPOpt and solved with SCIP under a time limit, warm-started with
   the heuristic incumbent. SCIP's dual bound certifies how far any schedule can be from optimal.
3. Final schedule = the best schedule by the independent evaluator ({best['source']}).

Runs:
{chr(10).join(run_lines)}

## Solution status

- Final objective (recomputed from schedule.csv): {fmt(metrics['objective'])}
- Best bound (max SCIP dual bound over runs): {fmt(best_bound)}
- Absolute gap: {fmt(gaps['absolute_gap'])}; relative gap (abs / max(1,|incumbent|)): {fmt(gaps['relative_gap'])}
- Certificate: {certified}

## Extraction and audit

The schedule is read from the incumbent's y variables (value > 0.5), written to schedule.csv,
re-loaded from disk, checked for hard rules (each block exactly once, each slot exactly once,
front-loading), and every metric is recomputed by a pure evaluator that uses only the input data
and that file. metrics.json is written from that evaluator and round-trip checked.
"""
    with open(os.path.join(out_dir, "formulation.md"), "w") as f:
        f.write(formulation)

    sched_lines = "\n".join(f"| {s} | {inst['raw_of'][b]} |" for s, b in zip(inst["slot_raw"], best["schedule_blocks"]))
    report = f"""# Exam block sequencing report

## Final objective

**{fmt(metrics['objective'])}** (minimization), recomputed from `schedule.csv`. Certificate: {certified}.
Best bound {fmt(best_bound)}, absolute gap {fmt(gaps['absolute_gap'])}, relative gap {fmt(gaps['relative_gap'])}.

## Score breakdown

| component | count | weight | weighted |
|---|---|---|---|
{chr(10).join(comp_rows)}
| **objective** | | | **{fmt(metrics['objective'])}** |

Overlap rule: `{rule}` = {RULE_TEXT[rule]} for each four-slot window whose first two slots both
start qualifying three-slot windows.

## Feasibility check (from the written schedule.csv)

- {inst['n']} rows, one per slot; every slot filled exactly once: yes
- Every block appears exactly once (no duplicates, none missing): yes
- Front-loading ({'active' if inst['frontload_active'] else 'inactive'}): large blocks all in early slots: {'yes' if large_ok else 'NO'}
- Virtual blocks scheduled as normal blocks: {inst['virtual'] or 'none in this instance'}
- Loader warnings: {inst['warnings'] or 'none'}

## Solution method

Hybrid: parallel simulated annealing + iterated local search for an incumbent, then the compact
MIP (assignment y, ordered arc p, big-M triple-window costs c) solved by SCIP (PySCIPOpt) under a
time limit, warm-started with that incumbent. Final schedule source: {best['source']}.
See `formulation.md` for the model and run log.

{chr(10).join(run_lines)}

## Schedule

| slot | block |
|---|---|
{sched_lines}
"""
    with open(os.path.join(out_dir, "report.md"), "w") as f:
        f.write(report)

    files = [sched_path, met_path, os.path.join(out_dir, "formulation.md"), os.path.join(out_dir, "report.md")]
    sc.emit({"metrics": metrics, "feasibility": feas, "output_files": files})


if __name__ == "__main__":
    main()
