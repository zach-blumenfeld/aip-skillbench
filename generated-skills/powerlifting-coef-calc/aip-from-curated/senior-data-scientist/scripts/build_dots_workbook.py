#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "polars==1.37.1",
#   "fastexcel==0.18.0",
#   "xlsxwriter==3.2.9",
# ]
# ///
"""Write a copy of an OpenPowerlifting workbook with a populated "Dots" sheet.

The Dots sheet preserves source column order from the Data sheet:

  A: Name              ← =Data!<src>{row}
  B: Sex               ← =Data!<src>{row}
  C: BodyweightKg      ← =Data!<src>{row}
  D: Best3SquatKg      ← =Data!<src>{row}
  E: Best3BenchKg      ← =Data!<src>{row}
  F: Best3DeadliftKg   ← =Data!<src>{row}
  G: TotalKg           ← =D{row}+E{row}+F{row}
  H: Dots              ← =ROUND(IF(B{row}="M", male_poly, female_poly), 3)

Polynomial constants and bodyweight clamps are from the OpenPowerlifting
`coefficients/src` crate; see references/dots_formula.md.

Run via:
  uv run scripts/build_dots_workbook.py \\
    --input-path /root/data/openipf.xlsx \\
    --output-path /root/data/openipf_dots.xlsx
"""

from __future__ import annotations

import argparse
import json
import sys

import polars as pl
import xlsxwriter

# OpenPowerlifting Dots polynomial coefficients (quartic in bodyweight).
MALE = {
    "a": -0.0000010930,
    "b": 0.0007391293,
    "c": -0.1918759221,
    "d": 24.0900756,
    "e": -307.75076,
    "bw_min": 40,
    "bw_max": 210,
}
FEMALE = {
    "a": -0.0000010706,
    "b": 0.0005158568,
    "c": -0.1126655495,
    "d": 13.6175032,
    "e": -57.96288,
    "bw_min": 40,
    "bw_max": 150,
}

REQUIRED = [
    "Name",
    "Sex",
    "BodyweightKg",
    "Best3SquatKg",
    "Best3BenchKg",
    "Best3DeadliftKg",
]


def _poly_expr(coef: dict, bw_cell: str) -> str:
    bw = f"MAX({coef['bw_min']},MIN({coef['bw_max']},{bw_cell}))"
    return (
        f"({coef['a']}*POWER({bw},4)"
        f"+{coef['b']}*POWER({bw},3)"
        f"+{coef['c']}*POWER({bw},2)"
        f"+{coef['d']}*{bw}"
        f"+{coef['e']})"
    )


def dots_formula(sex_cell: str, bw_cell: str, total_cell: str) -> str:
    male = f"{total_cell}*(500/{_poly_expr(MALE, bw_cell)})"
    female = f"{total_cell}*(500/{_poly_expr(FEMALE, bw_cell)})"
    return f'=ROUND(IF({sex_cell}="M",{male},{female}),3)'


def build(input_path: str, output_path: str) -> dict:
    df = pl.read_excel(input_path, sheet_name="Data")
    data_columns = list(df.columns)
    missing = [c for c in REQUIRED if c not in data_columns]
    if missing:
        raise ValueError(
            f"Data sheet missing required columns: {missing}. Found: {data_columns}"
        )

    # 1-based source-column index per required header.
    src_index = {c: data_columns.index(c) + 1 for c in REQUIRED}

    def col_letter(idx_1: int) -> str:
        from string import ascii_uppercase

        n = idx_1
        out = ""
        while n > 0:
            n, rem = divmod(n - 1, 26)
            out = ascii_uppercase[rem] + out
        return out

    src_letter = {c: col_letter(src_index[c]) for c in REQUIRED}

    num_rows = df.height

    with xlsxwriter.Workbook(output_path) as wb:
        # Rewrite the Data sheet verbatim so the output is a self-contained workbook.
        data_ws = wb.add_worksheet("Data")
        for col_idx, name in enumerate(data_columns):
            data_ws.write(0, col_idx, name)
        for row_idx, row in enumerate(df.iter_rows()):
            for col_idx, value in enumerate(row):
                data_ws.write(row_idx + 1, col_idx, value)

        dots_ws = wb.add_worksheet("Dots")
        headers = REQUIRED + ["TotalKg", "Dots"]
        for col_idx, header in enumerate(headers):
            dots_ws.write(0, col_idx, header)

        # Rows are 1-indexed in Excel; data starts at row 2.
        for excel_row in range(2, num_rows + 2):
            # A..F: cross-sheet references to the matching Data cell.
            for dots_col_idx, name in enumerate(REQUIRED):
                cell = f"=Data!{src_letter[name]}{excel_row}"
                dots_ws.write_formula(excel_row - 1, dots_col_idx, cell)
            # G: TotalKg = D + E + F
            dots_ws.write_formula(
                excel_row - 1, 6, f"=D{excel_row}+E{excel_row}+F{excel_row}"
            )
            # H: Dots
            dots_ws.write_formula(
                excel_row - 1,
                7,
                dots_formula(f"B{excel_row}", f"C{excel_row}", f"G{excel_row}"),
            )

    return {"output_path": output_path, "rows_written": num_rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-path", required=True)
    parser.add_argument("--output-path", required=True)
    args = parser.parse_args()
    result = build(args.input_path, args.output_path)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
