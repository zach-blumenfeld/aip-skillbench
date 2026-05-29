"""Template: accessing and filtering DataFrame rows / columns and the common
per-row arithmetic the simulation loop needs.

Copy / adapt into your task code. The skill teaches patterns; this file is a
reference snippet, not an invoked library.

Key idioms:
  - Scalar NaN test → `pd.isna(value)`. Used inside the simulation loop to
    decide cruise (no lead) vs follow (lead present) mode.
  - Whole-column mask → `df['col'].notna()` / `df['col'].isna()`.
  - Boolean filter → `df[df['col'] > x]`; combine masks with `&` / `|` and
    wrap each comparison in parentheses.
  - Per-row iteration → `df.iterrows()`. Returns (index, row); access cells
    by column name. Fine for ~thousands of rows (1501 in the ACC task);
    vectorize for larger datasets.
"""
import pandas as pd


def select_columns(df, cols):
    """Subset a DataFrame to a list of columns, preserving order."""
    return df[cols]


def filter_time_window(df, t_start, t_end, time_col="time"):
    """Return rows where t_start <= time < t_end."""
    return df[(df[time_col] >= t_start) & (df[time_col] < t_end)]


def filter_not_null(df, col):
    """Return rows where `col` is not NaN."""
    return df[df[col].notna()]


def add_diff_column(df, a, b, out):
    """Add a column `out` = df[a] - df[b]. Returns the modified DataFrame."""
    df[out] = df[a] - df[b]
    return df


def iterate_sensor_rows(df):
    """Yield (time, ego_speed, lead_speed_or_None, distance_or_None) per row.

    Mirrors how simulation.py walks sensor_data.csv: NaN lead values become
    Python None so downstream `lead_speed is None` checks work cleanly.
    """
    for _, row in df.iterrows():
        lead_speed = None if pd.isna(row["lead_speed"]) else row["lead_speed"]
        distance = None if pd.isna(row["distance"]) else row["distance"]
        yield row["time"], row["ego_speed"], lead_speed, distance


def column_stats(df, col):
    """Return mean / max / min / std for a column — handy for acc_report.md."""
    series = df[col]
    return {
        "mean": series.mean(),
        "max": series.max(),
        "min": series.min(),
        "std": series.std(),
    }


if __name__ == "__main__":
    import sys

    df = pd.read_csv(sys.argv[1], na_values=["", "NA", "null"])
    print("rows with lead vehicle:", len(filter_not_null(df, "lead_speed")))
    print("ego_speed stats:", column_stats(df, "ego_speed"))
