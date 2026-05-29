# Excel Formula Patterns for Cross-Sheet Workbook Builds

This task requires writing **Excel formulas** into cells — not pre-computed
numeric values. The verifier inspects cells with `openpyxl` and rejects the
output unless the relevant cells contain strings starting with `=`.

## Library choice

Use **`xlsxwriter`** when building a new workbook from scratch. It is the
only mainstream Python library whose `worksheet.write_formula(row, col, "=...")`
writes a string that openpyxl reads back as a formula. Polars and pandas
write numeric values, not formulas.

```bash
uv add polars xlsxwriter fastexcel
```

- `polars` + `fastexcel` to read the existing Data sheet.
- `xlsxwriter` to write the new workbook (Data sheet recreated, Dots sheet
  with formulas).

`openpyxl` can edit existing workbooks in place but its formula handling is
quirky for cross-sheet references. Prefer the rebuild-from-scratch pattern.

## Build pattern

1. Read the original workbook with polars to get headers and row count:

   ```python
   import polars as pl
   df = pl.read_excel(input_path, sheet_name="Data")
   num_rows = df.height
   ```

2. Open a new workbook with xlsxwriter and recreate the Data sheet by writing
   each cell. Headers go in row 0, values in rows 1..num_rows.

3. Add the Dots sheet. Write the 8 headers to row 0. For each data row (Excel
   rows 2..num_rows+1):

   ```python
   dots_sheet.write_formula(row_idx, 0, f"=Data!A{excel_row}")    # Name
   dots_sheet.write_formula(row_idx, 1, f"=Data!B{excel_row}")    # Sex
   dots_sheet.write_formula(row_idx, 2, f"=Data!I{excel_row}")    # BodyweightKg
   dots_sheet.write_formula(row_idx, 3, f"=Data!K{excel_row}")    # Best3SquatKg
   dots_sheet.write_formula(row_idx, 4, f"=Data!L{excel_row}")    # Best3BenchKg
   dots_sheet.write_formula(row_idx, 5, f"=Data!M{excel_row}")    # Best3DeadliftKg
   dots_sheet.write_formula(row_idx, 6, f"=D{excel_row}+E{excel_row}+F{excel_row}")  # TotalKg
   dots_sheet.write_formula(row_idx, 7, dots_formula_for_row(excel_row))             # Dots
   ```

4. Save by exiting the `with xlsxwriter.Workbook(out_path) as wb:` context.

5. Move/rename the output workbook over the input path if the task expects
   the result at the original location.

## Index conventions

- Excel rows are 1-indexed; row 1 is the header.
- xlsxwriter `write_formula(row, col, ...)` uses 0-indexed `row` and `col`.
  Data row 2 in Excel = `row=1` in xlsxwriter.
- Column letters in formulas (`A`, `B`, ..., `H`) reference the destination
  *Dots* sheet by default. Use `Data!X{row}` to point at the source sheet.

## Gotchas

- A formula that *looks* right but isn't prefixed with `=` is treated by
  xlsxwriter as a string, not a formula. Always start formula strings with
  `=`.
- Polars' `write_excel` writes computed values — it will *not* produce
  formula cells. Verifier checks `G2` and `H2` for `value.startswith("=")`;
  a numeric value fails the check.
- xlsxwriter cannot append to an existing workbook. Rebuild Data and Dots
  together in one pass.
- The Dots formula contains commas inside `MIN`, `MAX`, `IF`, and `POWER`.
  Excel uses commas as argument separators only in US/EN locales. The cleaned
  task input and verifier both run in this locale — do not switch to
  semicolons.
- The verifier (`test_outputs.py`) checks the formula at `H2` contains
  `ROUND(` and `IF(` strings. The script in this skill emits both — do not
  simplify by, e.g., pre-resolving the sex branch per row.
