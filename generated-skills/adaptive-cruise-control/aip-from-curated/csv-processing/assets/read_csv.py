"""Template: read a CSV file into a pandas DataFrame with explicit NA handling.

Copy / adapt into your task code (e.g., simulation.py reading sensor_data.csv).
The skill teaches patterns; this file is a reference snippet, not an invoked
library.

Rules enforced:
  - Always pass `na_values=['', 'NA', 'null']` so blank cells and common
    sentinels parse to NaN — pandas's default treats '' as NaN but not 'NA'
    or 'null'.
  - Use `pd.isna(value)` to test scalars (e.g., a single row's column) — the
    `is None` / `== nan` checks both fail on NumPy NaN.
  - Use `df['col'].notna()` (or `.isna()`) to mask whole columns.
"""
import pandas as pd


def read_csv(path):
    """Read a CSV with blank / 'NA' / 'null' cells coerced to NaN."""
    return pd.read_csv(path, na_values=["", "NA", "null"])


def missing_summary(df):
    """Return a Series of NaN counts per column — useful before processing."""
    return df.isnull().sum()


if __name__ == "__main__":
    import sys

    df = read_csv(sys.argv[1])
    print(df.head())
    print("rows:", len(df))
    print("columns:", df.columns.tolist())
    print("missing per column:")
    print(missing_summary(df))
