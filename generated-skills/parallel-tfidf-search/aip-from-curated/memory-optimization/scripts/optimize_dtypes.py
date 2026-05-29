"""Mechanical dtype downcasting for a pandas DataFrame.

Downcasts int64 / float64 columns to the smallest safe numeric width, converts
low-cardinality object columns to `category`, and demotes float columns that
hold only integral values (with NaN) to nullable `Int64`. Pure deterministic
rules; no judgment calls — adapt the resulting code rather than tuning here.

Usage:
    uv run scripts/optimize_dtypes.py <input.csv|input.parquet> [--inplace-suffix .opt]

Or import:
    from optimize_dtypes import optimize_dataframe
    df = optimize_dataframe(df, category_threshold=0.5)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


def optimize_dataframe(df: pd.DataFrame, category_threshold: float = 0.5) -> pd.DataFrame:
    """Return a memory-optimized copy of ``df``.

    Rules (applied in order):
      1. int64 columns -> smallest int via ``pd.to_numeric(downcast='integer')``
      2. float64 columns -> smallest float via ``pd.to_numeric(downcast='float')``
      3. object columns with unique-ratio < ``category_threshold`` -> ``category``
      4. float columns whose non-NaN values are all integral -> nullable ``Int64``
    """
    out = df.copy()

    for col in out.select_dtypes(include=["int64"]).columns:
        out[col] = pd.to_numeric(out[col], downcast="integer")

    for col in out.select_dtypes(include=["float64"]).columns:
        out[col] = pd.to_numeric(out[col], downcast="float")

    for col in out.select_dtypes(include=["object"]).columns:
        total = len(out[col])
        if total == 0:
            continue
        unique_ratio = out[col].nunique(dropna=True) / total
        if unique_ratio < category_threshold:
            out[col] = out[col].astype("category")

    for col in out.select_dtypes(include=["float"]).columns:
        non_null = out[col].dropna()
        if len(non_null) > 0 and non_null.apply(float.is_integer).all():
            out[col] = out[col].astype("Int64")

    return out


def _memory_summary(df: pd.DataFrame) -> dict:
    usage = df.memory_usage(deep=True)
    return {
        "total_bytes": int(usage.sum()),
        "by_column": {col: int(usage[col]) for col in df.columns},
    }


def _load(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported input extension: {suffix}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("input", type=Path, help="CSV or Parquet input file")
    p.add_argument(
        "--category-threshold",
        type=float,
        default=0.5,
        help="Unique-ratio cutoff below which object columns become categorical (default 0.5).",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the optimized DataFrame to (CSV or Parquet, by extension).",
    )
    args = p.parse_args(argv)

    df = _load(args.input)
    before = _memory_summary(df)
    out = optimize_dataframe(df, category_threshold=args.category_threshold)
    after = _memory_summary(out)

    report = {
        "input": str(args.input),
        "rows": int(len(out)),
        "before_bytes": before["total_bytes"],
        "after_bytes": after["total_bytes"],
        "reduction_ratio": (
            1.0 - after["total_bytes"] / before["total_bytes"]
            if before["total_bytes"] > 0
            else 0.0
        ),
        "dtypes_before": {c: str(t) for c, t in df.dtypes.items()},
        "dtypes_after": {c: str(t) for c, t in out.dtypes.items()},
    }
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")

    if args.output is not None:
        suffix = args.output.suffix.lower()
        if suffix == ".csv":
            out.to_csv(args.output, index=False)
        elif suffix in {".parquet", ".pq"}:
            out.to_parquet(args.output, index=False)
        else:
            raise ValueError(f"Unsupported output extension: {suffix}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
