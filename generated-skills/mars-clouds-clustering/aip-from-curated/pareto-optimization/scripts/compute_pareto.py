#!/usr/bin/env python3
"""Compute the Pareto frontier from a CSV of multi-objective results.

A row is **Pareto-optimal** (non-dominated) when no other row is at least
as good on every objective and strictly better on at least one. Improving
any single objective from a Pareto-optimal row requires giving up
something on another.

Usage (CLI)::

    python compute_pareto.py --input results.csv --output pareto.csv \\
        --maximize F1 --minimize delta \\
        --filter "F1 > 0.5" \\
        --sort-by F1

Usage (module)::

    from compute_pareto import pareto_frontier
    frontier = pareto_frontier(df, maximize=["F1"], minimize=["delta"])

Tries the ``paretoset`` library first (handles ties cleanly) and falls
back to a vectorized numpy implementation when paretoset is unavailable.
"""
import argparse
import operator
import sys

import numpy as np
import pandas as pd


_OPS = {
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    "<": operator.lt,
}


def pareto_frontier(df, maximize=None, minimize=None):
    """Return rows of ``df`` that are Pareto-optimal on the given objectives.

    Parameters
    ----------
    df : pandas.DataFrame
        Candidate rows. Non-objective columns are preserved on the output.
    maximize : list of str, optional
        Columns to maximize.
    minimize : list of str, optional
        Columns to minimize.

    Returns
    -------
    pandas.DataFrame
        The non-dominated rows, original column order preserved, index reset.
    """
    maximize = list(maximize or [])
    minimize = list(minimize or [])
    if not (maximize or minimize):
        raise ValueError("Specify at least one column in --maximize or --minimize")

    objectives = maximize + minimize
    senses = ["max"] * len(maximize) + ["min"] * len(minimize)

    missing = [c for c in objectives if c not in df.columns]
    if missing:
        raise KeyError(f"Objective columns not found in input: {missing}")

    if len(df) == 0:
        return df.reset_index(drop=True)

    try:
        from paretoset import paretoset

        mask = paretoset(df[objectives], sense=senses)
        return df[mask].reset_index(drop=True)
    except ImportError:
        return _pareto_numpy(df, objectives, senses)


def _pareto_numpy(df, objectives, senses):
    """Vectorized numpy fallback. Negates minimize-cols so all are 'maximize'."""
    obj = df[objectives].to_numpy(dtype=float).copy()
    for i, s in enumerate(senses):
        if s == "min":
            obj[:, i] = -obj[:, i]

    n = obj.shape[0]
    is_efficient = np.ones(n, dtype=bool)
    for i in range(n):
        if not is_efficient[i]:
            continue
        # Anyone that i dominates: i >= them on every objective, and > on at least one.
        ge = (obj[i] >= obj).all(axis=1)
        gt = (obj[i] > obj).any(axis=1)
        dominated = ge & gt
        is_efficient &= ~dominated
        is_efficient[i] = True  # i itself stays in
    return df[is_efficient].reset_index(drop=True)


def parse_filter(expr, df):
    """Parse a simple filter like ``'F1 >= 0.5'``. Returns a boolean mask."""
    for op_str in (">=", "<=", "==", "!=", ">", "<"):
        if op_str in expr:
            col, val = expr.split(op_str, 1)
            col, val = col.strip(), val.strip()
            if col not in df.columns:
                raise KeyError(f"Filter column not found: {col!r}")
            return _OPS[op_str](df[col], float(val))
    raise ValueError(f"Could not parse filter expression: {expr!r}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compute the Pareto frontier from a CSV of multi-objective results."
    )
    parser.add_argument("--input", required=True, help="Input CSV path.")
    parser.add_argument("--output", required=True, help="Output CSV path.")
    parser.add_argument(
        "--maximize",
        nargs="*",
        default=[],
        help="Column names to maximize (space-separated).",
    )
    parser.add_argument(
        "--minimize",
        nargs="*",
        default=[],
        help="Column names to minimize (space-separated).",
    )
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        metavar="EXPR",
        help="Pre-filter rows, e.g. \"F1 > 0.5\". Repeatable; ANDed together.",
    )
    parser.add_argument(
        "--sort-by",
        help="Sort output by this column descending after frontier extraction.",
    )
    parser.add_argument(
        "--round",
        action="append",
        default=[],
        metavar="COL:DECIMALS",
        help=(
            "Round a column to N decimals on output, e.g. 'F1:5' or "
            "'shape_weight:1'. Repeatable."
        ),
    )
    parser.add_argument(
        "--columns",
        nargs="*",
        default=None,
        help="Explicit output column order (subset/reorder of input columns).",
    )
    args = parser.parse_args(argv)

    df = pd.read_csv(args.input)
    for expr in args.filter:
        df = df[parse_filter(expr, df)].reset_index(drop=True)

    frontier = pareto_frontier(df, maximize=args.maximize, minimize=args.minimize)

    if args.sort_by:
        if args.sort_by not in frontier.columns:
            print(
                f"WARNING: --sort-by column {args.sort_by!r} not in output; skipping sort",
                file=sys.stderr,
            )
        else:
            frontier = frontier.sort_values(args.sort_by, ascending=False).reset_index(
                drop=True
            )

    for spec in args.round:
        if ":" not in spec:
            raise ValueError(f"--round expects COL:DECIMALS, got {spec!r}")
        col, decimals = spec.split(":", 1)
        col = col.strip()
        if col in frontier.columns:
            frontier[col] = frontier[col].round(int(decimals))

    if args.columns:
        missing = [c for c in args.columns if c not in frontier.columns]
        if missing:
            raise KeyError(f"--columns references unknown columns: {missing}")
        frontier = frontier[args.columns]

    frontier.to_csv(args.output, index=False)
    print(
        f"Pareto frontier: {len(frontier)} of {len(df)} filtered points -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
