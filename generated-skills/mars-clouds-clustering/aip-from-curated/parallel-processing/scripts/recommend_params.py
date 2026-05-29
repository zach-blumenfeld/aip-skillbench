#!/usr/bin/env python3
"""Recommend joblib.Parallel parameters from task properties.

Encodes the lookup-table and threshold rules from the source skill:
- backend: 'loky' for CPU-bound, 'threading' for I/O-bound
- n_jobs: -1 (all cores) by default
- verbose: 10 if the caller wants progress, 0 otherwise
- worth_parallelizing: False when per-item work is too small to amortize
  joblib's process-startup + serialization overhead (~0.1s/item rule).

Usage:
    python recommend_params.py --task-type cpu_bound --n-items 770 \
        --seconds-per-item 0.5 --progress
"""

from __future__ import annotations

import argparse
import json
import sys

MIN_SECONDS_PER_ITEM = 0.1  # joblib overhead floor from source skill
VERBOSE_PROGRESS = 10
VERBOSE_SILENT = 0


def recommend(
    task_type: str,
    n_items: int,
    seconds_per_item: float,
    progress: bool,
    n_jobs: int = -1,
) -> dict:
    task_type = task_type.lower().replace("-", "_")
    if task_type not in {"cpu_bound", "io_bound"}:
        raise ValueError(
            f"task_type must be 'cpu_bound' or 'io_bound', got {task_type!r}"
        )
    if n_items < 1:
        raise ValueError(f"n_items must be >= 1, got {n_items}")
    if seconds_per_item < 0:
        raise ValueError(
            f"seconds_per_item must be >= 0, got {seconds_per_item}"
        )

    backend = "loky" if task_type == "cpu_bound" else "threading"
    verbose = VERBOSE_PROGRESS if progress else VERBOSE_SILENT
    worth_parallelizing = seconds_per_item >= MIN_SECONDS_PER_ITEM

    warnings = []
    if not worth_parallelizing:
        warnings.append(
            f"Per-item work ({seconds_per_item:.3f}s) is below the "
            f"{MIN_SECONDS_PER_ITEM}s/item threshold; joblib overhead "
            "may exceed savings. Consider running sequentially."
        )
    if n_items == 1:
        warnings.append("Only 1 item — no benefit from parallelization.")

    est_sequential_s = n_items * seconds_per_item

    return {
        "n_jobs": n_jobs,
        "backend": backend,
        "verbose": verbose,
        "worth_parallelizing": worth_parallelizing,
        "estimated_sequential_seconds": est_sequential_s,
        "warnings": warnings,
        "snippet": (
            f"Parallel(n_jobs={n_jobs}, backend={backend!r}, "
            f"verbose={verbose})"
        ),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--task-type",
        required=True,
        choices=["cpu_bound", "io_bound", "cpu-bound", "io-bound"],
        help="Whether the per-item work is CPU- or I/O-bound.",
    )
    p.add_argument("--n-items", type=int, required=True)
    p.add_argument(
        "--seconds-per-item",
        type=float,
        required=True,
        help="Estimated wall-clock seconds for one item, sequentially.",
    )
    p.add_argument(
        "--progress",
        action="store_true",
        help="Emit progress messages (verbose=10) instead of silent (0).",
    )
    p.add_argument(
        "--n-jobs",
        type=int,
        default=-1,
        help="Workers; -1 uses all cores (default).",
    )
    args = p.parse_args()

    try:
        out = recommend(
            task_type=args.task_type,
            n_items=args.n_items,
            seconds_per_item=args.seconds_per_item,
            progress=args.progress,
            n_jobs=args.n_jobs,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
