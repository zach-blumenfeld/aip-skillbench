#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "openpyxl==3.1.5",
# ]
# ///
"""Inspect an OpenPowerlifting workbook.

Emits a JSON object on stdout with sheet names, the Data-sheet column headers
in source order, and the data-row count (excluding header). openpyxl is used
in read-only mode so empty sibling sheets (e.g. an empty "Dots") do not
trigger spurious errors.

Run via:
  uv run scripts/inspect_workbook.py --input-path /root/data/openipf.xlsx
"""

from __future__ import annotations

import argparse
import json
import sys

import openpyxl


def inspect(input_path: str) -> dict:
    wb = openpyxl.load_workbook(input_path, read_only=True, data_only=True)
    sheet_names = list(wb.sheetnames)
    if "Data" not in sheet_names:
        raise ValueError(
            f"Workbook is missing a 'Data' sheet. Sheets present: {sheet_names}"
        )
    ws = wb["Data"]

    header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
    data_columns = [c for c in header_row if c is not None]

    # max_row counts the header; subtract 1 for data rows.
    row_count = max(0, (ws.max_row or 0) - 1)
    return {
        "sheet_names": sheet_names,
        "data_columns": data_columns,
        "data_row_count": int(row_count),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-path", required=True, help="Path to input .xlsx")
    args = parser.parse_args()

    result = inspect(args.input_path)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
