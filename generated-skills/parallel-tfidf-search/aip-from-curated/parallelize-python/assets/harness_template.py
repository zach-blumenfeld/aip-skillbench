#!/usr/bin/env python3
"""Verification harness: sequential baseline vs optimized code on the same input.

Copy to a scratch directory (NOT the deliverable folder), edit the FILL-IN blocks,
run with the same python the task uses:  PYTHONDONTWRITEBYTECODE=1 python harness.py
(the env var keeps __pycache__ out of the deliverable folder; delete any that appears).
Prints one JSON object shaped like the `verification` answer. Each public function is
timed separately (FUNCTIONS); `speedups` is the one the task's threshold names (PRIMARY).
"""

import dataclasses
import json
import math
import os
import resource
import statistics
import sys
import time
import traceback

# FILL-IN 1: make the baseline and the deliverable importable.
sys.path.insert(0, "/path/to/workspace")
# from sequential import build_index_sequential, search_sequential
# from parallel_solution import build_index_parallel, search_parallel

WORKER_COUNTS = [1, 2, 4]   # requirements.worker_counts
REPEATS = 3                 # best-of-N after one warm-up
REL_TOL, ABS_TOL = 1e-9, 1e-12  # floats; use 0/0 when the task demands identical results


def make_input():
    # FILL-IN 2: build the input exactly as the tests would (baseline generator/loader + seed, task size).
    raise NotImplementedError


# FILL-IN 3: one entry per public function: name -> (sequential_call(data), parallel_call(data, workers)).
# Each call returns everything the tests could compare (whole result objects, all fields, order included).
# Precompute shared inputs (e.g. the index a search runs against) inside make_input so each entry times one function.
FUNCTIONS = {
    # "build": (lambda d: build_index_sequential(d["docs"]), lambda d, w: build_index_parallel(d["docs"], num_workers=w)),
    # "search": (lambda d: search_sequential(d["queries"], d["index"]), lambda d, w: search_parallel(d["queries"], d["index"], num_workers=w)),
}
PRIMARY = None  # name of the function the task's speedup threshold applies to (default: first entry)


def measure_chunk_costs(worker_fn, chunks):
    """Balance metrics without instrumenting the deliverable: run the deliverable's own chunk
    worker on its own chunks in-process and time each one. Example:
        import parallel_solution as m
        chunks = m._make_chunks(items, workers)        # whatever the deliverable uses
        secs = measure_chunk_costs(m._worker, chunks)
        v["load_imbalance"], v["straggler_ratio"], v["worker_utilization"] = balance_metrics(secs, workers)
    """
    secs = []
    for c in chunks:
        t = time.perf_counter()
        worker_fn(c)
        secs.append(time.perf_counter() - t)
    return secs


def deep_diff(a, b, path="$", out=None, limit=20):
    """List the first `limit` differences between two nested results (dataclasses, dicts, lists, sets, floats)."""
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if dataclasses.is_dataclass(a) and dataclasses.is_dataclass(b):
        if type(a) is not type(b):
            out.append(f"{path}: type {type(a).__name__} != {type(b).__name__}")
            return out
        for f in dataclasses.fields(a):
            deep_diff(getattr(a, f.name), getattr(b, f.name), f"{path}.{f.name}", out, limit)
        return out
    if isinstance(a, float) or isinstance(b, float):
        if not (isinstance(a, (int, float)) and isinstance(b, (int, float))) or not math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL):
            out.append(f"{path}: {a!r} != {b!r}")
        return out
    if type(a) is not type(b):
        out.append(f"{path}: type {type(a).__name__} != {type(b).__name__}")
        return out
    if isinstance(a, dict):
        if a.keys() != b.keys():
            out.append(f"{path}: keys differ, only-left={list(a.keys() - b.keys())[:5]} only-right={list(b.keys() - a.keys())[:5]}")
        for k in list(a.keys() & b.keys()):
            deep_diff(a[k], b[k], f"{path}[{k!r}]", out, limit)
            if len(out) >= limit:
                break
        return out
    if isinstance(a, (list, tuple)):
        if len(a) != len(b):
            out.append(f"{path}: len {len(a)} != {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            deep_diff(x, y, f"{path}[{i}]", out, limit)
            if len(out) >= limit:
                break
        return out
    if a != b:
        out.append(f"{path}: {str(a)[:80]} != {str(b)[:80]}")
    return out


def best_time(fn, *args):
    fn(*args)  # warm-up
    times, result = [], None
    for _ in range(REPEATS):
        t = time.perf_counter()
        result = fn(*args)
        times.append(time.perf_counter() - t)
    return min(times), result


def balance_metrics(chunk_seconds, workers):
    """chunk_seconds: per-task durations recorded by the worker function (return them alongside results while testing)."""
    if not chunk_seconds:
        return None, None, None
    loads = [0.0] * workers
    for t in sorted(chunk_seconds, reverse=True):  # approximates dynamic scheduling
        loads[loads.index(min(loads))] += t
    avg = sum(loads) / workers
    imbalance = max(loads) / avg if avg else 1.0
    straggler = max(chunk_seconds) / statistics.median(chunk_seconds)
    utilization = avg / max(loads) if max(loads) else 1.0
    return round(imbalance, 3), round(straggler, 3), round(utilization, 3)


def peak_mb():
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(r / (1 << 20) if sys.platform == "darwin" else r / 1024, 1)


def main():
    v = {"outputs_match": False, "comparison_detail": "", "timings": {"parallel_seconds": {}}, "speedups": {}, "per_function": {},
         "errors": [], "load_imbalance": None, "straggler_ratio": None, "worker_utilization": None}
    try:
        data = make_input()
        primary = PRIMARY or next(iter(FUNCTIONS))
        diffs = []
        for name, (seq_fn, par_fn) in FUNCTIONS.items():
            seq_t, seq_out = best_time(seq_fn, data)
            fv = {"sequential_seconds": round(seq_t, 4), "parallel_seconds": {}, "speedups": {}}
            for w in WORKER_COUNTS:
                par_t, par_out = best_time(par_fn, data, w)
                fv["parallel_seconds"][str(w)] = round(par_t, 4)
                fv["speedups"][str(w)] = round(seq_t / par_t, 3)
                diffs += [f"{name} workers={w} {x}" for x in deep_diff(seq_out, par_out)]
            v["per_function"][name] = fv
            if name == primary:
                v["timings"] = {"sequential_seconds": fv["sequential_seconds"], "parallel_seconds": fv["parallel_seconds"]}
                v["speedups"] = fv["speedups"]
        v["outputs_match"] = not diffs
        v["comparison_detail"] = "all equal" if not diffs else "; ".join(diffs[:10])
        v["peak_memory_mb"] = peak_mb()  # parent only and cumulative; measure baseline vs new in separate processes when memory matters
    except Exception:  # noqa: BLE001
        v["errors"].append(traceback.format_exc()[-1500:])
    print(json.dumps(v, indent=2))


if __name__ == "__main__":
    main()
