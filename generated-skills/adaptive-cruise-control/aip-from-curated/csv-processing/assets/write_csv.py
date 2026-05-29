"""Template: write a pandas DataFrame to CSV, either from a dict of columns
or by accumulating per-step records and converting at the end.

Copy / adapt into your task code (e.g., simulation.py writing
simulation_results.csv). The skill teaches patterns; this file is a reference
snippet, not an invoked library.

Rules enforced:
  - `index=False` — never emit pandas's row index as a CSV column unless the
    task explicitly asks for it.
  - Use Python `None` (or `float('nan')`) in record dicts for missing values;
    pandas serializes both as empty fields, matching expected outputs like
    `0.0,0.0,3.0,cruise,,,` where distance_error / distance / ttc are blank.
  - Column order in the written CSV matches dict insertion order — build
    each record with the exact key order the task's expected output uses.
"""
import pandas as pd


def write_csv_from_dict(columns, path):
    """Write a CSV from a dict-of-lists ({'time': [...], 'value': [...]})."""
    df = pd.DataFrame(columns)
    df.to_csv(path, index=False)


def write_csv_from_records(records, path):
    """Write a CSV from a list of row-dicts.

    Each record's keys define the column set (and order, on Python 3.7+).
    None / NaN values become empty cells in the output.
    """
    df = pd.DataFrame(records)
    df.to_csv(path, index=False)


if __name__ == "__main__":
    # Example shape matching the ACC task's simulation_results.csv:
    #   time,ego_speed,acceleration_cmd,mode,distance_error,distance,ttc
    # When mode == 'cruise' (no lead vehicle), distance_error / distance / ttc
    # are written as blank cells via None.
    records = [
        {
            "time": 0.0,
            "ego_speed": 0.0,
            "acceleration_cmd": 3.0,
            "mode": "cruise",
            "distance_error": None,
            "distance": None,
            "ttc": None,
        },
        {
            "time": 0.1,
            "ego_speed": 0.3,
            "acceleration_cmd": 3.0,
            "mode": "cruise",
            "distance_error": None,
            "distance": None,
            "ttc": None,
        },
    ]
    write_csv_from_records(records, "simulation_results.csv")
