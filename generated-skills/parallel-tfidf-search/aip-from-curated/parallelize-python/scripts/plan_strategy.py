#!/usr/bin/env python3
"""Turn the classification + measurements into a concrete parallelization plan.

stdin:  {"currentState": {...}, "assets": {"strategy_rules": <json text>}, "expects": [...]}
stdout: {"plan": {...}, "route": "parallelize" | "optimize_sequential"}

Encodes the three source decision trees (parallelization, load balancing, memory) as
lookups in assets/strategy_rules.json, simulates partitioning strategies on the measured
per-item weights, and applies Amdahl / over-parallelization / CPU-quota checks.
"""

import heapq
import json
import math
import os
import statistics
import sys


def load_rules(assets):
    raw = (assets or {}).get("strategy_rules")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        return json.loads(raw)
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "..", "assets", "strategy_rules.json")) as f:
        return json.load(f)


def imbalance(loads):
    loads = [x for x in loads]
    avg = sum(loads) / len(loads) if loads else 0
    return round(max(loads) / avg, 3) if avg else 1.0


def sim_contiguous(w, k):
    n = len(w)
    return [sum(w[i * n // k:(i + 1) * n // k]) for i in range(k)]


def sim_round_robin(w, k):
    return [sum(w[i::k]) for i in range(k)]


def sim_lpt(w, k):
    heap = [(0.0, i) for i in range(k)]
    loads = [0.0] * k
    for x in sorted(w, reverse=True):
        load, i = heapq.heappop(heap)
        loads[i] = load + x
        heapq.heappush(heap, (loads[i], i))
    return loads


def sim_dynamic(w, k, chunk):
    """Pool.map-style: contiguous chunks of `chunk` items handed to whichever worker frees first."""
    tasks = [sum(w[i:i + chunk]) for i in range(0, len(w), chunk)]
    heap = [(0.0, i) for i in range(k)]
    loads = [0.0] * k
    for t in tasks:
        load, i = heapq.heappop(heap)
        loads[i] = load + t
        heapq.heappush(heap, (loads[i], i))
    return loads, len(tasks)


def weight_profile(w):
    if not w:
        return None
    s = sorted(w)
    med = s[len(s) // 2] or 1e-12
    mean = statistics.fmean(s)
    cv = statistics.pstdev(s) / mean if mean else 0.0
    ratio = s[-1] / med
    if cv < 0.25:
        suggested = "uniform"
    elif ratio > 20 or s[-1] > 0.05 * sum(s):
        suggested = "long_tail"
    else:
        suggested = "variable_predictable"
    return {"n": len(s), "min": s[0], "median": med, "mean": round(mean, 3), "max": s[-1],
            "cv": round(cv, 3), "max_over_median": round(ratio, 2), "suggested_variance_class": suggested}


def as_int_list(x):
    if isinstance(x, list):
        return [int(v) for v in x if isinstance(v, (int, float)) and v >= 1]
    if isinstance(x, (int, float)) and x >= 1:
        return [int(x)]
    return []


def main():
    payload = json.load(sys.stdin)
    st = payload.get("currentState", payload)
    rules = load_rules(payload.get("assets"))
    T = rules["targets"]

    wtype = st.get("workload_type", "cpu_bound")
    variance = st.get("task_variance", "variable_unpredictable")
    dep = st.get("dependency", "independent")
    goal = st.get("goal", "speed")
    big_shared = bool(st.get("large_shared_input", False))
    exact = bool(st.get("exact_match_required", True))
    analysis = st.get("analysis") or {}
    env = analysis.get("environment") or {}
    static = analysis.get("static") or {}
    workload = st.get("workload") or {}
    req = st.get("requirements") or {}

    usable = int(env.get("usable_cpus") or os.cpu_count() or 1)
    stdlib_only = bool(env.get("stdlib_only", False))
    fork = bool(env.get("fork_available", False))
    numpy_ok = bool((env.get("packages") or {}).get("numpy"))

    requested = as_int_list(req.get("worker_counts"))
    worker_counts = requested or [usable]
    notes, warnings = [], []
    over = [k for k in worker_counts if k > usable]
    if over:
        warnings.append(f"Requested worker counts {over} exceed usable CPUs ({usable}); speedup will plateau near {usable}x of the parallel part. Still accept the requested value in the API.")

    # --- executor (parallelization tree) ---
    eff_type = wtype
    if wtype == "data_parallel" and not numpy_ok:
        eff_type = "cpu_bound"
        notes.append(rules["no_numeric_libs_fallback"])
    executor = rules["executor"].get(eff_type, rules["executor"]["cpu_bound"]).get(dep, rules["executor"]["cpu_bound"]["independent"])
    if stdlib_only and eff_type in ("cpu_bound", "mixed"):
        notes.append("Only the standard library is guaranteed: implement with multiprocessing / concurrent.futures, no third-party packages.")

    shared = None
    if big_shared:
        shared = rules["shared_input"]["fork" if fork else "no_fork"]
        if fork:
            notes.append("Fork is available here but is not the default on Python 3.14+/macOS: request it explicitly with multiprocessing.get_context('fork') and fall back to an initializer when it is unavailable.")

    # --- balancing ---
    weights = [float(x) for x in (workload.get("item_weights") or []) if isinstance(x, (int, float))]
    wp = weight_profile(weights)
    if wp and wp["suggested_variance_class"] != variance and not (variance == "variable_unpredictable" and wp["suggested_variance_class"] != "uniform"):
        warnings.append(f"Measured weights suggest '{wp['suggested_variance_class']}' (cv={wp['cv']}, max/median={wp['max_over_median']}) but the decision said '{variance}'; prefer the measurement when weights are a good cost proxy.")
    balancing = rules["balancing"].get(variance, rules["balancing"]["variable_unpredictable"])

    sims = {}
    n_items = int(workload.get("num_items") or (len(weights) if weights else 0))
    recommended_chunks = {}
    best = None
    if weights:
        total_w, max_w = sum(weights), max(weights)
        counts_by_k = {}
        for k in sorted(set(worker_counts + [usable])):
            if k < 2:
                continue
            # ~chunks_per_worker x k chunks, but never so many that the largest item outweighs an average chunk
            cap = int(total_w // max_w) if max_w else len(weights)
            nch = max(k, min(k * T["chunks_per_worker"], cap, len(weights)))
            recommended_chunks[str(k)] = nch
            dyn_chunk = max(1, math.ceil(len(weights) / nch))
            dyn, ntasks = sim_dynamic(weights, k, dyn_chunk)
            chunk_counts = {"contiguous_equal_chunks": k, "round_robin": k, "lpt_k_chunks": k,
                            f"lpt_{nch}_chunks_largest_first_dynamic": nch, f"in_order_chunks_of_{dyn_chunk}_dynamic": ntasks}
            counts_by_k[str(k)] = chunk_counts
            sims[str(k)] = {
                "contiguous_equal_chunks": imbalance(sim_contiguous(weights, k)),
                "round_robin": imbalance(sim_round_robin(weights, k)),
                "lpt_k_chunks": imbalance(sim_lpt(weights, k)),
                f"lpt_{nch}_chunks_largest_first_dynamic": imbalance(sim_dynamic_lpt(weights, k, nch)),
                f"in_order_chunks_of_{dyn_chunk}_dynamic": imbalance(dyn),
            }
        best = {}
        for k, s_ in sims.items():
            # Weights are only a proxy: among near-best options prefer LPT chunks handed out dynamically
            # (absorbs proxy error), then static LPT, then the simple static splits.
            lo = min(s_.values())
            order = sorted(s_, key=lambda n: (0 if n.startswith("lpt_") and n.endswith("dynamic") else 1 if n == "lpt_k_chunks" else 2, s_[n]))
            name = next(n for n in order if s_[n] <= lo + 0.02)
            best[k] = {"strategy": name, "imbalance": s_[name], "chunks": counts_by_k[k][name]}
            if s_[name] > T["load_imbalance_max"]:
                warnings.append(f"At {k} workers no item-level partition gets under {T['load_imbalance_max']} imbalance (best {s_[name]}): the largest items must be split into subtasks.")
        notes.append("Imbalance = max(worker load)/mean(worker load) by item weight; target < %.1f. Use best_balance[W] (strategy + number of chunks); near-ties go to LPT chunks handed out dynamically because the weights are only a cost proxy. Chunk counts are capped at total_weight/max_item_weight so one huge item never sits in an overfull chunk." % T["load_imbalance_max"])
        notes.append("If the required API has a chunk_size parameter, treat it as an upper bound on items per chunk and honour it alongside these counts.")
    else:
        warnings.append("No item_weights measured; balancing advice is from the decision only. Measure a cost proxy per item (e.g. len(text)) to size chunks.")

    chunks_per_worker = T["chunks_per_worker"]

    # --- Amdahl ---
    p = workload.get("parallel_fraction")
    if fixes_pending := bool([h for h in static.get("hotspots", []) if not h.get("likely_input_generation")]):
        notes.append("amdahl_max_speedup_parallelism_alone uses the baseline's parallel_fraction, before algorithmic fixes; removing quadratic serial work raises the ceiling.")
    amdahl = None
    if isinstance(p, (int, float)) and 0 <= p <= 1:
        amdahl = {str(k): round(1 / ((1 - p) + p / min(k, usable)), 2) for k in worker_counts}
        ms = req.get("min_speedup")
        if isinstance(ms, dict):
            need = {str(k): v for k, v in ms.items() if isinstance(v, (int, float))}
        elif isinstance(ms, (int, float)):
            need = {str(k): ms for k in worker_counts if k > 1}
        else:
            need = {}
        for k, target in need.items():
            bound = 1 / ((1 - p) + p / min(int(k), usable)) if k.isdigit() else max(amdahl.values())
            if bound < target and not fixes_pending:
                warnings.append(f"Amdahl bound at {k} workers with parallel_fraction={p} is {bound:.2f}x < required {target}x: shrink the serial part first (linear merge, move per-item work into workers) — parallelizing the current code cannot reach the target.")
            elif bound < target:
                warnings.append(f"Parallelism alone caps at {bound:.2f}x at {k} workers (< required {target}x): the algorithmic fixes in algorithmic_fixes_first are mandatory, not optional.")

    # --- algorithmic fixes first ---
    fixes, ignored = [], []
    for h in static.get("hotspots", []):
        (ignored if h.get("likely_input_generation") else fixes).append(f"{h.get('file')}:{h.get('line')} in {h.get('function')}: {h.get('kind')} ({h.get('outer', '')} x {h.get('inner', '')}) — {h.get('hint')}")
    for l in static.get("lambdas_to_pool", []):
        fixes.append(f"{l['file']}:{l['line']}: {l['hint']}")

    # --- memory ---
    mem = list(rules["memory_tactics"]["always"])
    if goal in ("memory", "both"):
        mem += rules["memory_tactics"]["memory_goal"]
        cls = static.get("classes_without_slots", [])
        if cls:
            mem.append("Classes without __slots__ (candidates if many instances exist): " + ", ".join(f"{c['class']} ({c['file']}:{c['line']})" for c in cls[:10]))
    limit = (env.get("memory") or {}).get("limit_mb")
    peak = workload.get("peak_memory_mb")
    if isinstance(limit, (int, float)) and isinstance(peak, (int, float)) and limit:
        per_worker_copy = peak * max(worker_counts)
        if not big_shared and per_worker_copy > 0.7 * limit:
            warnings.append(f"Copying the ~{peak} MB working set into {max(worker_counts)} workers (~{int(per_worker_copy)} MB) approaches the {limit} MB limit: share read-only data (fork/initializer/shared memory) and send slices.")

    # --- route ---
    must = bool(req.get("must_parallelize", False))
    small = (n_items and n_items < T["small_workload_items"]) and (float(workload.get("baseline_seconds") or 0) < T["small_workload_seconds"])
    if goal == "memory" and not must:
        route, why = "optimize_sequential", "Goal is memory reduction, not speed."
    elif dep == "loop_carried" and not must:
        route, why = "optimize_sequential", "Iterations depend on each other; no safe parallel decomposition."
    elif small and not must:
        route, why = "optimize_sequential", "Workload too small: parallel overhead would exceed the gain (over-parallelization)."
    else:
        route, why = "parallelize", "Independent or mergeable work large enough to amortize pool overhead" + (" (task requires a parallel implementation)." if must else ".")
    if small and must:
        warnings.append("Workload is small: keep a sequential fast path for tiny inputs or num_workers == 1 so the parallel API is never slower than the baseline there.")

    plan = {
        "route_reason": why,
        "worker_counts": worker_counts,
        "usable_cpus": usable,
        "executor": executor,
        "shared_input": shared,
        "balancing": balancing,
        "resource_constraints": rules["resource_constraints"],
        "chunks_per_worker": chunks_per_worker,
        "weight_profile": wp,
        "balance_simulation": sims or None,
        "best_balance": best,
        "amdahl_max_speedup_parallelism_alone": amdahl,
        "recommended_chunks": recommended_chunks or None,
        "algorithmic_fixes_first": fixes,
        "hotspots_in_input_generation_ignore": ignored,
        "memory_tactics": mem,
        "exactness": rules["exactness"] if exact else ["Results may differ in order/float noise only where the task allows; document the tolerance used."],
        "pitfalls": rules["pitfalls"],
        "verification_checklist": rules["verification_checklist"],
        "targets": {k: T[k] for k in ("load_imbalance_max", "straggler_ratio_max", "worker_utilization_min")},
        "notes": notes,
        "warnings": warnings,
    }
    print(json.dumps({"plan": plan, "route": route}))


def sim_dynamic_lpt(w, k, nchunks):
    """LPT-pack items into nchunks balanced chunks, then schedule chunks dynamically on k workers."""
    chunk_loads = sim_lpt(w, max(1, min(nchunks, len(w))))
    heap = [(0.0, i) for i in range(k)]
    loads = [0.0] * k
    for t in sorted(chunk_loads, reverse=True):
        load, i = heapq.heappop(heap)
        loads[i] = load + t
        heapq.heappush(heap, (loads[i], i))
    return loads


if __name__ == "__main__":
    main()
