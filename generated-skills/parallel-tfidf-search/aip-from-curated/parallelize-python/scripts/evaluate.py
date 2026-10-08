#!/usr/bin/env python3
"""Grade the measured verification of the optimized code against the targets.

stdin:  {"currentState": {"verification": {...}, "requirements": {...}, "plan": {...}, "attempt"?: int}, ...}
stdout: {"verdict": {...}, "verdict_status": "pass" | "revise" | "stop", "attempt": int}

Failures (block "pass"): outputs differ, errors, missing API, speedup below the required
or below 1x at the largest worker count, memory over limit / not reduced when memory is the goal.
Warnings: monitoring metrics outside targets (imbalance, stragglers, utilization), slow at 1
worker, unchecked checklist items.
"""

import json
import os
import sys


def num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def main():
    payload = json.load(sys.stdin)
    st = payload.get("currentState", payload)
    v = st.get("verification") or {}
    req = st.get("requirements") or {}
    plan = st.get("plan") or {}
    targets = plan.get("targets") or {"load_imbalance_max": 1.2, "straggler_ratio_max": 2.0, "worker_utilization_min": 0.9}
    max_attempts = 3
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "assets", "strategy_rules.json")) as f:
            max_attempts = json.load(f)["targets"]["max_attempts"]
    except Exception:  # noqa: BLE001
        pass
    goal = st.get("goal", "speed")
    failures, warnings = [], []

    if v.get("outputs_match") is not True:
        failures.append("Outputs do not match the sequential baseline (or were not compared): " + str(v.get("comparison_detail", "no detail")))
    errs = v.get("errors") or []
    if errs:
        failures.append(f"{len(errs)} error(s) during verification: " + "; ".join(str(e)[:200] for e in errs[:5]))
    if v.get("api_ok") is False:
        failures.append("Required API/deliverable missing or signature mismatch: " + str(v.get("api_detail", "")))

    # speedups
    timings = v.get("timings") or {}
    seq = num(timings.get("sequential_seconds"))
    par = timings.get("parallel_seconds") or {}
    speedups = {str(k): num(s) for k, s in (v.get("speedups") or {}).items() if num(s) is not None}
    if seq:
        for k, t in par.items():
            if num(t):
                speedups.setdefault(str(k), round(seq / num(t), 3))
    min_sp = req.get("min_speedup")
    if goal in ("speed", "both"):
        if not speedups:
            failures.append("No speedup measured: time sequential vs parallel on the same input at the task's worker counts.")
        else:
            keyed = {str(k): num(x) for k, x in min_sp.items()} if isinstance(min_sp, dict) else None
            for k, s in speedups.items():
                need = keyed.get(k) if keyed else (num(min_sp) if num(min_sp) and k != "1" else None)
                if need and s < need:
                    failures.append(f"Speedup {s}x at {k} workers is below the required {need}x.")
            top = max(speedups, key=lambda k: int(k) if k.isdigit() else 0)
            if speedups[top] <= 1.0:
                failures.append(f"Parallel version is not faster at {top} workers ({speedups[top]}x).")
            if "1" in speedups and speedups["1"] < 0.8:
                warnings.append(f"At 1 worker the new code is {speedups['1']}x the baseline; add a sequential fast path for num_workers == 1 / tiny inputs.")

    # every public function measured separately
    for fname, fv in (v.get("per_function") or {}).items():
        sp = {str(k): num(x) for k, x in ((fv or {}).get("speedups") or {}).items() if num(x) is not None}
        if not sp:
            continue
        top = max(sp, key=lambda k: int(k) if k.isdigit() else 0)
        need = None
        mf = (fv or {}).get("min_speedup")
        if isinstance(mf, (int, float)):
            need = mf
        if need and sp[top] < need:
            failures.append(f"{fname}: speedup {sp[top]}x at {top} workers is below the required {need}x.")
        elif sp[top] < 1.0:
            warnings.append(f"{fname}: not faster at {top} workers ({sp[top]}x) on the measured input; acceptable only if the input is too small to amortize a pool (sequential fast path).")

    # monitoring metrics
    if st.get("route", "parallelize") == "parallelize" and goal in ("speed", "both") and all(v.get(k) is None for k in ("load_imbalance", "straggler_ratio", "worker_utilization")):
        warnings.append("No balance metrics measured: time each chunk in-process (harness measure_chunk_costs) and report load_imbalance / straggler_ratio / worker_utilization.")
    li = num(v.get("load_imbalance"))
    if li is not None and li > targets["load_imbalance_max"]:
        warnings.append(f"Load imbalance {li} > {targets['load_imbalance_max']}: rebalance (weighted/LPT chunks, largest first, more chunks per worker).")
    sr = num(v.get("straggler_ratio"))
    if sr is not None and sr > targets["straggler_ratio_max"]:
        warnings.append(f"Straggler ratio {sr} > {targets['straggler_ratio_max']}: split the largest tasks or schedule them first.")
    wu = num(v.get("worker_utilization"))
    if wu is not None and wu < targets["worker_utilization_min"]:
        warnings.append(f"Worker utilization {wu} < {targets['worker_utilization_min']}: the serial part or IPC dominates; shrink the parent's merge and the pickled payloads.")

    # memory
    peak = num(v.get("peak_memory_mb"))
    base_peak = num(v.get("baseline_peak_memory_mb"))
    limit = num(req.get("memory_limit_mb"))
    if peak is not None and limit is not None and peak > limit:
        failures.append(f"Peak memory {peak} MB exceeds the limit {limit} MB.")
    if goal in ("memory", "both"):
        if peak is None or base_peak is None:
            failures.append("Memory goal but peak memory of baseline and new code not both measured.")
        elif peak >= base_peak:
            failures.append(f"Peak memory not reduced ({peak} MB vs baseline {base_peak} MB).")

    unchecked = [k for k, ok in (v.get("checklist") or {}).items() if ok is not True]
    if unchecked:
        warnings.append("Checklist items not confirmed: " + "; ".join(unchecked[:10]))

    attempt = int(st.get("attempt") or 0) + 1
    if not failures:
        status = "pass"
    elif attempt >= max_attempts:
        status = "stop"
    else:
        status = "revise"
    verdict = {"passed": not failures, "failures": failures, "warnings": warnings, "speedups": speedups, "attempt": attempt, "max_attempts": max_attempts}
    print(json.dumps({"verdict": verdict, "verdict_status": status, "attempt": attempt}))


if __name__ == "__main__":
    main()
