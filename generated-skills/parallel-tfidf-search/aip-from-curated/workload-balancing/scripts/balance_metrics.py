"""Compute load-balance metrics from per-worker timing/queue measurements.

Usage:
    uv run scripts/balance_metrics.py --json '<measurements-json>'
    uv run scripts/balance_metrics.py --file measurements.json

Input JSON shape (all fields optional, but at least one of `worker_times`
or `worker_loads` is required):

    {
      "worker_times":  [12.4, 11.9, 18.7, 12.1],   # seconds per worker
      "worker_loads":  [102, 98, 145, 95],         # work units per worker
      "queue_lengths": [3, 5, 12, 2],              # queue depth samples
      "wall_clock":    19.0                        # total wall-clock seconds
    }

Outputs single JSON object on stdout with whichever metrics could be
computed and a `verdict` per metric against the targets from the skill:

    load_imbalance     = max(load)  / mean(load)         target < 1.2
    straggler_ratio    = max(time)  / median(time)       target < 2.0
    worker_utilization = mean(time) / wall_clock          target > 0.9
    queue_depth_stddev = stdev(queue_lengths)             target: low

Exits non-zero if input is invalid.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path


TARGETS = {
    "load_imbalance": ("<", 1.2),
    "straggler_ratio": ("<", 2.0),
    "worker_utilization": (">", 0.9),
}


def _verdict(metric: str, value: float) -> str:
    target = TARGETS.get(metric)
    if not target:
        return "informational"
    op, threshold = target
    ok = (value < threshold) if op == "<" else (value > threshold)
    return f"{'pass' if ok else 'fail'} (target {op} {threshold})"


def compute(measurements: dict) -> dict:
    out: dict = {}

    times = measurements.get("worker_times")
    loads = measurements.get("worker_loads")
    queues = measurements.get("queue_lengths")
    wall = measurements.get("wall_clock")

    if not times and not loads and queues is None:
        raise ValueError(
            "Provide at least one of worker_times, worker_loads, or queue_lengths."
        )

    if loads:
        mean_load = statistics.fmean(loads)
        if mean_load > 0:
            value = max(loads) / mean_load
            out["load_imbalance"] = {
                "value": round(value, 4),
                "verdict": _verdict("load_imbalance", value),
                "note": "max(load) / mean(load); >1.2 indicates skew.",
            }

    if times:
        med = statistics.median(times)
        if med > 0:
            value = max(times) / med
            out["straggler_ratio"] = {
                "value": round(value, 4),
                "verdict": _verdict("straggler_ratio", value),
                "note": "max(time) / median(time); >2.0 indicates a straggler.",
            }
        if wall and wall > 0:
            value = statistics.fmean(times) / wall
            out["worker_utilization"] = {
                "value": round(value, 4),
                "verdict": _verdict("worker_utilization", value),
                "note": "mean(busy_time) / wall_clock; <0.9 means idle workers.",
            }

    if queues is not None and len(queues) >= 2:
        value = statistics.stdev(queues)
        out["queue_depth_stddev"] = {
            "value": round(value, 4),
            "verdict": _verdict("queue_depth_stddev", value),
            "note": "stdev of queue depth samples; low is healthy.",
        }

    failing = [m for m, payload in out.items() if "fail" in payload["verdict"]]
    out["_summary"] = {
        "metrics_computed": list(k for k in out.keys() if not k.startswith("_")),
        "failing": failing,
        "balanced": not failing,
    }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--json", help="measurements as a JSON string")
    src.add_argument("--file", help="path to a JSON file with measurements")
    args = parser.parse_args(argv)

    raw = args.json if args.json else Path(args.file).read_text()
    try:
        measurements = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"invalid JSON: {e}", file=sys.stderr)
        return 1

    try:
        result = compute(measurements)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
