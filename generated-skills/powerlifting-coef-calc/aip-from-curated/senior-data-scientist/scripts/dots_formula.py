#!/usr/bin/env python3
"""
Dots formula generator and Excel workbook builder.

Subcommands:
  formula     Emit the Excel ROUND/IF/POWER formula for one Dots cell, given
              cell references for Sex, BodyweightKg, and TotalKg.
  build       Build the output workbook end-to-end: recreate the Data sheet
              and fill the Dots sheet with formulas referencing Data.

The formula encodes the IPF/OpenPowerlifting Dots polynomial. Coefficient
values and bodyweight clamps are documented in references/dots-formula.md.

Usage:
  python scripts/dots_formula.py formula --sex B2 --bw C2 --total G2
  python scripts/dots_formula.py build  --input /root/data/openipf.xlsx \\
                                        --output /root/data/openipf.xlsx
"""

import argparse
import sys

# IPF Dots polynomial coefficients (a*bw^4 + b*bw^3 + c*bw^2 + d*bw + e).
MALE_COEF = (-0.0000010930, 0.0007391293, -0.1918759221, 24.0900756, -307.75076)
FEMALE_COEF = (-0.0000010706, 0.0005158568, -0.1126655495, 13.6175032, -57.96288)
MALE_BW_BOUNDS = (40, 210)
FEMALE_BW_BOUNDS = (40, 150)

# Headers for the Dots sheet, in order. Used by `build`.
DOTS_HEADERS = [
    "Name",
    "Sex",
    "BodyweightKg",
    "Best3SquatKg",
    "Best3BenchKg",
    "Best3DeadliftKg",
    "TotalKg",
    "Dots",
]

# Header names this skill expects on the Data sheet. `build` looks these up by
# name (not column letter) so it tolerates column reordering in the input.
DATA_HEADERS_NEEDED = {
    "Name": "Name",
    "Sex": "Sex",
    "BodyweightKg": "BodyweightKg",
    "Best3SquatKg": "Best3SquatKg",
    "Best3BenchKg": "Best3BenchKg",
    "Best3DeadliftKg": "Best3DeadliftKg",
}


def _branch(coef, bounds, bw_cell, total_cell):
    a, b, c, d, e = coef
    lo, hi = bounds
    clamped = f"MAX({lo},MIN({hi},{bw_cell}))"
    poly = (
        f"({a}*POWER({clamped},4)"
        f"+{b}*POWER({clamped},3)"
        f"+{c}*POWER({clamped},2)"
        f"+{d}*{clamped}"
        f"+{e})"
    )
    return f"{total_cell}*(500/{poly})"


def dots_formula(sex_cell: str, bw_cell: str, total_cell: str) -> str:
    """Return the Excel formula string for one Dots cell."""
    male = _branch(MALE_COEF, MALE_BW_BOUNDS, bw_cell, total_cell)
    female = _branch(FEMALE_COEF, FEMALE_BW_BOUNDS, bw_cell, total_cell)
    return f'=ROUND(IF({sex_cell}="M",{male},{female}),3)'


def _col_letter(idx_zero: int) -> str:
    """Convert a 0-indexed column to its Excel letter (A, B, ..., Z, AA, ...)."""
    letters = ""
    n = idx_zero
    while True:
        letters = chr(ord("A") + n % 26) + letters
        n = n // 26 - 1
        if n < 0:
            break
    return letters


def build(input_path: str, output_path: str) -> None:
    """Build a new workbook with a Data sheet and a formula-driven Dots sheet."""
    import polars as pl
    import xlsxwriter

    df = pl.read_excel(input_path, sheet_name="Data")
    columns = list(df.columns)

    missing = [h for h in DATA_HEADERS_NEEDED if h not in columns]
    if missing:
        raise SystemExit(
            f"Data sheet is missing required headers: {missing}. "
            f"Found columns: {columns}"
        )

    # Map header -> Excel column letter on the Data sheet (by header position).
    data_col_letter = {h: _col_letter(columns.index(h)) for h in DATA_HEADERS_NEEDED}
    n_rows = df.height
    print(f"Loaded {n_rows} rows; {len(columns)} columns from {input_path}", flush=True)

    with xlsxwriter.Workbook(output_path) as wb:
        data_sheet = wb.add_worksheet("Data")
        for ci, name in enumerate(columns):
            data_sheet.write(0, ci, name)
        for ri, row in enumerate(df.iter_rows()):
            for ci, value in enumerate(row):
                data_sheet.write(ri + 1, ci, value)

        dots_sheet = wb.add_worksheet("Dots")
        for ci, header in enumerate(DOTS_HEADERS):
            dots_sheet.write(0, ci, header)

        # Dots layout (1-indexed for Excel):
        # A=Name, B=Sex, C=BodyweightKg, D=Best3SquatKg, E=Best3BenchKg,
        # F=Best3DeadliftKg, G=TotalKg, H=Dots
        for excel_row in range(2, n_rows + 2):
            dots_sheet.write_formula(
                excel_row - 1, 0, f"=Data!{data_col_letter['Name']}{excel_row}"
            )
            dots_sheet.write_formula(
                excel_row - 1, 1, f"=Data!{data_col_letter['Sex']}{excel_row}"
            )
            dots_sheet.write_formula(
                excel_row - 1, 2, f"=Data!{data_col_letter['BodyweightKg']}{excel_row}"
            )
            dots_sheet.write_formula(
                excel_row - 1, 3, f"=Data!{data_col_letter['Best3SquatKg']}{excel_row}"
            )
            dots_sheet.write_formula(
                excel_row - 1, 4, f"=Data!{data_col_letter['Best3BenchKg']}{excel_row}"
            )
            dots_sheet.write_formula(
                excel_row - 1, 5, f"=Data!{data_col_letter['Best3DeadliftKg']}{excel_row}"
            )
            dots_sheet.write_formula(
                excel_row - 1, 6, f"=D{excel_row}+E{excel_row}+F{excel_row}"
            )
            dots_sheet.write_formula(
                excel_row - 1, 7, dots_formula(f"B{excel_row}", f"C{excel_row}", f"G{excel_row}")
            )

    print(f"Wrote {output_path} (Data + Dots with {n_rows} formula rows)", flush=True)


def main(argv=None):
    p = argparse.ArgumentParser(description="Dots formula generator / workbook builder")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("formula", help="Emit the Excel formula for one Dots cell.")
    f.add_argument("--sex", required=True, help="Excel cell reference for Sex (e.g. B2).")
    f.add_argument("--bw", required=True, help="Excel cell reference for BodyweightKg (e.g. C2).")
    f.add_argument("--total", required=True, help="Excel cell reference for TotalKg (e.g. G2).")

    b = sub.add_parser("build", help="Build the output workbook end-to-end.")
    b.add_argument("--input", required=True, help="Path to input openipf.xlsx.")
    b.add_argument("--output", required=True, help="Path to output xlsx.")

    args = p.parse_args(argv)
    if args.cmd == "formula":
        print(dots_formula(args.sex, args.bw, args.total))
        return 0
    if args.cmd == "build":
        build(args.input, args.output)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
