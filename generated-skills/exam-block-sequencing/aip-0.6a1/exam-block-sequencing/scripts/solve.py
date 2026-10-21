"""Steps solve and refine: hybrid heuristic incumbent, then SCIP MIP warm-started from it.

solve  (no `solve_summary` in state) -> emits `solve_summary`
refine (`solve_summary` in state)    -> doubles the budgets, seeds from the stored best, emits `refine_summary`
Both keep work_dir/best.json (the best schedule so far, by the pure evaluator) and append to
work_dir/runs.json (every heuristic and MIP run with its certificate).
"""
import json
import os
import time

import seqcore as sc


def _load(path, default):
    if os.path.isfile(path):
        with open(path) as f:
            return json.load(f)
    return default


def main():
    st = sc.read_stdin()
    refine = "solve_summary" in st
    data_dir, work_dir = st["data_dir"], st["work_dir"]
    weights, rule = st["objective_weights"], st["overlap_rule"]
    h_sec = int(st["heuristic_seconds"]) * (2 if refine else 1)
    m_sec = int(st["mip_seconds"]) * (2 if refine else 1)
    os.makedirs(work_dir, exist_ok=True)
    best_path, runs_path = os.path.join(work_dir, "best.json"), os.path.join(work_dir, "runs.json")
    inst = sc.load_instance(data_dir)
    pt, tt = sc.build_terms(inst, weights, rule)
    idx, labels = inst["idx"], inst["labels"]
    prev = _load(best_path, None) if refine else None
    seeds = [[idx[b] for b in prev["schedule_blocks"]]] if prev else None
    phase = "refine" if refine else "solve"
    t0 = time.time()

    h = sc.parallel_search(data_dir, weights, rule, h_sec, base_seed=(1000 if refine else 0), seeds_from=seeds)
    h_metrics = sc.evaluate(h["perm"], inst, weights, rule)
    if sc.check_feasible(h["perm"], inst):
        sc.fail(f"heuristic produced an infeasible schedule: {sc.check_feasible(h['perm'], inst)}")

    mip = sc.build_and_solve_mip(inst, pt, tt, m_sec, warm_perm=h["perm"])
    cands = [("heuristic", h["perm"], h_metrics)]
    mip_rec = {k: v for k, v in mip.items() if k != "perm"}
    if mip.get("perm") is not None:
        mm = sc.evaluate(mip["perm"], inst, weights, rule)
        mip_rec["evaluator_objective_of_incumbent"] = mm["objective"]
        mip_rec["solver_objective_matches_evaluator"] = abs(mm["objective"] - mip["incumbent_objective"]) < 1e-6
        if not sc.check_feasible(mip["perm"], inst):
            cands.insert(0, ("mip_incumbent", mip["perm"], mm))  # preferred on ties
        else:
            mip_rec["error"] = f"MIP incumbent failed feasibility: {sc.check_feasible(mip['perm'], inst)}"
    src, perm, metrics = min(cands, key=lambda c: c[2]["objective"])
    if prev and prev["metrics"]["objective"] <= metrics["objective"]:
        kept = "previous best kept (not improved)"
        src, perm, metrics = prev["source"], [idx[b] for b in prev["schedule_blocks"]], prev["metrics"]
    else:
        kept = "new best stored"
        with open(best_path, "w") as f:
            json.dump({"source": f"{phase}:{src}", "schedule_blocks": [labels[b] for b in perm],
                       "metrics": metrics, "overlap_rule": rule}, f, indent=2)
        src = f"{phase}:{src}"

    runs = _load(runs_path, [])
    runs.append({"phase": phase, "heuristic": {k: v for k, v in h.items() if k != "perm"},
                 "heuristic_objective": h_metrics["objective"], "mip": mip_rec,
                 "heuristic_seconds_budget": h_sec, "mip_seconds_budget": m_sec})
    with open(runs_path, "w") as f:
        json.dump(runs, f, indent=2, default=str)

    bounds = [r["mip"].get("best_bound") for r in runs if r["mip"].get("best_bound") is not None]
    best_bound = max(bounds) if bounds else None
    summary = {
        "phase": phase,
        "best_objective": metrics["objective"],
        "best_source": src,
        "store": kept,
        "heuristic_objective": h_metrics["objective"],
        "heuristic_workers": h["workers"],
        "heuristic_worker_best_costs": h["worker_best_costs"],
        "heuristic_workers_at_best": h["workers_at_best"],
        "heuristic_last_improvement_fraction": h["max_last_improvement_fraction"],
        "mip_status": mip.get("status"),
        "mip_error": mip_rec.get("error"),
        "mip_incumbent_objective": mip.get("incumbent_objective"),
        "mip_warm_start_accepted": mip.get("warm_start_accepted"),
        "best_bound": best_bound,
        "mip_bound_note": mip_rec.get("bound_note"),
        **sc.gap_fields(metrics["objective"], best_bound),
        "elapsed_seconds": round(time.time() - t0, 1),
        "heuristic_seconds_budget": h_sec,
        "mip_seconds_budget": m_sec,
    }
    sc.emit({("refine_summary" if refine else "solve_summary"): summary})


if __name__ == "__main__":
    main()
