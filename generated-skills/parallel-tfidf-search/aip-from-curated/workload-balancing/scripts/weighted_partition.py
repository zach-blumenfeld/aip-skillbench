"""Weighted partitioning via Longest-Processing-Time-first (LPT) bin packing.

Assigns each item to the currently least-loaded worker, processing items
from largest weight to smallest. Produces a list of worker bins, each a
list of items, where the total weight per bin is balanced.

Usage:
    uv run scripts/weighted_partition.py \\
        --items '["a","b","c","d"]' --weights '[3,1,4,1]' --workers 2

    uv run scripts/weighted_partition.py --file payload.json

Input file shape:
    {"items": [...], "weights": [...], "workers": 4}

Output JSON:
    {
      "assignments": [[items_for_worker_0], [items_for_worker_1], ...],
      "worker_loads": [w0_total, w1_total, ...],
      "load_imbalance": max(load)/mean(load),
      "perfectly_balanced": bool
    }

Notes:
- LPT is a 4/3-approximation to the optimal makespan; good enough whenever
  the agent has known or estimable per-item costs (e.g., document length,
  token count, file size).
- For variable/unknown costs use a dynamic queue or work stealing instead.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path


def partition(items: list, weights: list[float], num_workers: int) -> dict:
    if num_workers <= 0:
        raise ValueError("num_workers must be > 0")
    if len(items) != len(weights):
        raise ValueError("items and weights must be the same length")
    if not items:
        return {
            "assignments": [[] for _ in range(num_workers)],
            "worker_loads": [0.0] * num_workers,
            "load_imbalance": 1.0,
            "perfectly_balanced": True,
        }

    paired = sorted(zip(items, weights), key=lambda x: -x[1])
    bins: list[list] = [[] for _ in range(num_workers)]
    loads = [0.0] * num_workers
    for item, weight in paired:
        target = min(range(num_workers), key=lambda i: loads[i])
        bins[target].append(item)
        loads[target] += float(weight)

    mean_load = statistics.fmean(loads) if loads else 0.0
    imbalance = (max(loads) / mean_load) if mean_load > 0 else 1.0
    perfectly_balanced = max(loads) - min(loads) < 1e-9

    return {
        "assignments": bins,
        "worker_loads": [round(l, 6) for l in loads],
        "load_imbalance": round(imbalance, 6),
        "perfectly_balanced": perfectly_balanced,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--items", help="JSON list of items")
    p.add_argument("--weights", help="JSON list of numeric weights, parallel to items")
    p.add_argument("--workers", type=int, help="number of workers")
    p.add_argument("--file", help="JSON file with {items, weights, workers}")
    args = p.parse_args(argv)

    if args.file:
        payload = json.loads(Path(args.file).read_text())
        items, weights, workers = payload["items"], payload["weights"], payload["workers"]
    else:
        if not (args.items and args.weights and args.workers):
            print("provide --file OR --items + --weights + --workers", file=sys.stderr)
            return 1
        items = json.loads(args.items)
        weights = json.loads(args.weights)
        workers = args.workers

    try:
        result = partition(items, weights, workers)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
