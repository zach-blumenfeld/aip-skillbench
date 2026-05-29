"""Compute the Pareto frontier from a DataFrame or CSV.

Canonical implementation for the pareto-optimization skill. Uses the
`paretoset` library when available; falls back to a pure-numpy
implementation otherwise so the script runs in minimal environments.

Library usage
-------------
    from compute_pareto import compute_pareto_frontier
    pareto_df = compute_pareto_frontier(
        df,
        objectives=["accuracy", "latency_ms"],
        sense=["max", "min"],
        prefilter="accuracy >= 0.85",          # optional
        sort_by="accuracy",                    # optional
        sort_ascending=False,
        round_map={"accuracy": 5, "latency_ms": 5},  # optional
    )

CLI usage
---------
    python compute_pareto.py \\
        --input results.csv \\
        --objectives accuracy,latency_ms \\
        --sense max,min \\
        --prefilter "accuracy >= 0.85" \\
        --sort-by accuracy \\
        --sort-desc \\
        --round accuracy:5,latency_ms:5 \\
        --output pareto.csv

Inputs
------
- `objectives` and `sense` must be the same length. `sense` entries are
  either "max" or "min".
- `prefilter` is a pandas `DataFrame.query` expression applied BEFORE
  Pareto computation. Use it to drop low-quality results
  (e.g. `"F1 > 0.5"`).
- `round_map` maps column names to decimal places; applied to the final
  frontier before write.

Output
------
The frontier DataFrame retains every column of the input, not just the
objectives — caller can inspect the parameters that produced each
Pareto-optimal solution.
"""

from __future__ import annotations

import argparse
import sys
from typing import Iterable, Mapping

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def _paretoset_mask(objectives_df: pd.DataFrame, sense: list[str]) -> np.ndarray:
    """Use the `paretoset` library when available."""
    from paretoset import paretoset  # type: ignore[import-not-found]

    return np.asarray(paretoset(objectives_df, sense=sense), dtype=bool)


def _manual_pareto_mask(objectives_df: pd.DataFrame, sense: list[str]) -> np.ndarray:
    """Pure-numpy fallback. Flips minimize columns then keeps weakly-dominant
    points that are also strictly better than at least one neighbour."""
    arr = objectives_df.to_numpy(dtype=float, copy=True)
    for j, s in enumerate(sense):
        if s == "min":
            arr[:, j] = -arr[:, j]
        elif s != "max":
            raise ValueError(f"sense entries must be 'max' or 'min', got {s!r}")

    n = arr.shape[0]
    keep = np.ones(n, dtype=bool)
    for i in range(n):
        if not keep[i]:
            continue
        # other dominates i iff all(other >= i) and any(other > i)
        weakly_better = np.all(arr >= arr[i], axis=1)
        strictly_better = np.any(arr > arr[i], axis=1)
        dominated = weakly_better & strictly_better
        dominated[i] = False
        if dominated.any():
            keep[i] = False
    return keep


def pareto_mask(objectives_df: pd.DataFrame, sense: list[str]) -> np.ndarray:
    """Return a boolean mask flagging Pareto-optimal rows of `objectives_df`."""
    if len(sense) != objectives_df.shape[1]:
        raise ValueError(
            f"sense length {len(sense)} != objectives columns {objectives_df.shape[1]}"
        )
    try:
        return _paretoset_mask(objectives_df, sense)
    except ImportError:
        return _manual_pareto_mask(objectives_df, sense)


def compute_pareto_frontier(
    df: pd.DataFrame,
    objectives: list[str],
    sense: list[str],
    *,
    prefilter: str | None = None,
    sort_by: str | None = None,
    sort_ascending: bool = True,
    round_map: Mapping[str, int] | None = None,
) -> pd.DataFrame:
    """Compute the Pareto frontier of `df` over `objectives`.

    All non-objective columns are preserved so the caller can see the
    parameters that produced each frontier point.
    """
    missing = [c for c in objectives if c not in df.columns]
    if missing:
        raise KeyError(f"Objectives not in DataFrame: {missing}")

    working = df.query(prefilter) if prefilter else df
    if working.empty:
        return working.copy()

    mask = pareto_mask(working[objectives], sense)
    frontier = working.loc[mask].copy()

    if sort_by:
        frontier = frontier.sort_values(sort_by, ascending=sort_ascending)

    if round_map:
        for col, places in round_map.items():
            if col in frontier.columns:
                frontier[col] = frontier[col].round(places)

    return frontier.reset_index(drop=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_csv_list(raw: str) -> list[str]:
    return [tok.strip() for tok in raw.split(",") if tok.strip()]


def _parse_round_map(raw: str | None) -> dict[str, int] | None:
    if not raw:
        return None
    out: dict[str, int] = {}
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if ":" not in token:
            raise ValueError(f"--round token {token!r} missing ':'. Expected col:places")
        col, places = token.split(":", 1)
        out[col.strip()] = int(places)
    return out


def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Compute the Pareto frontier of a CSV.")
    p.add_argument("--input", required=True, help="Input CSV path.")
    p.add_argument(
        "--objectives", required=True,
        help="Comma-separated objective columns (e.g. 'accuracy,latency_ms').",
    )
    p.add_argument(
        "--sense", required=True,
        help="Comma-separated 'max' / 'min' per objective (same length as --objectives).",
    )
    p.add_argument(
        "--prefilter", default=None,
        help="Optional pandas .query() expression applied before Pareto computation.",
    )
    p.add_argument("--sort-by", default=None, help="Column to sort the frontier by.")
    p.add_argument(
        "--sort-desc", action="store_true",
        help="Sort descending (default ascending).",
    )
    p.add_argument(
        "--round", dest="round_map", default=None,
        help="Per-column rounding, e.g. 'accuracy:5,latency_ms:5'.",
    )
    p.add_argument("--output", required=True, help="Output CSV path for the frontier.")
    args = p.parse_args(list(argv) if argv is not None else None)

    df = pd.read_csv(args.input)
    objectives = _parse_csv_list(args.objectives)
    sense = _parse_csv_list(args.sense)

    frontier = compute_pareto_frontier(
        df,
        objectives=objectives,
        sense=sense,
        prefilter=args.prefilter,
        sort_by=args.sort_by,
        sort_ascending=not args.sort_desc,
        round_map=_parse_round_map(args.round_map),
    )

    frontier.to_csv(args.output, index=False)
    print(
        f"Wrote {len(frontier)} Pareto-optimal rows to {args.output} "
        f"(from {len(df)} input rows)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
