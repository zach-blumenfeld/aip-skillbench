#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Map the canonical Dots input columns to their positions in the Data sheet.

Required columns (preserved in source order, with header text unchanged):

  Name, Sex, BodyweightKg, Best3SquatKg, Best3BenchKg, Best3DeadliftKg

Emits a JSON list on stdout, one item per selected column:
  {"name": "Name", "source_index": 1, "source_letter": "A", "dots_index": 1, "dots_letter": "A"}

`source_index` is 1-based to match Excel addressing. Fails non-zero if any
required column is missing from the input header row.

Run via `uv run scripts/select_dots_columns.py --columns-json '["Name","Sex",...]'`
or `--columns-file path/to/columns.json`.
"""

from __future__ import annotations

import argparse
import json
import string
import sys

REQUIRED = [
    "Name",
    "Sex",
    "BodyweightKg",
    "Best3SquatKg",
    "Best3BenchKg",
    "Best3DeadliftKg",
]


def col_letter(idx_1: int) -> str:
    """1-based column index → Excel column letter (A, B, …, Z, AA)."""
    letters = ""
    n = idx_1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = string.ascii_uppercase[rem] + letters
    return letters


def select(data_columns: list[str]) -> list[dict]:
    missing = [c for c in REQUIRED if c not in data_columns]
    if missing:
        raise ValueError(
            f"Data sheet is missing required columns: {missing}. "
            f"Found columns: {data_columns}"
        )
    out = []
    for dots_index_0, name in enumerate(REQUIRED):
        src_index_1 = data_columns.index(name) + 1
        dots_index_1 = dots_index_0 + 1
        out.append(
            {
                "name": name,
                "source_index": src_index_1,
                "source_letter": col_letter(src_index_1),
                "dots_index": dots_index_1,
                "dots_letter": col_letter(dots_index_1),
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--columns-json", help="JSON array of column headers")
    group.add_argument("--columns-file", help="Path to JSON file with array")
    args = parser.parse_args()

    if args.columns_json:
        data_columns = json.loads(args.columns_json)
    else:
        with open(args.columns_file) as f:
            data_columns = json.load(f)

    selected = select(data_columns)
    json.dump(selected, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
