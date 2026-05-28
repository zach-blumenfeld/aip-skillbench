---
name: xlsx
description: "Comprehensive spreadsheet creation, editing, and analysis with support for formulas, formatting, data analysis, and visualization. When Claude needs to work with spreadsheets (.xlsx, .xlsm, .csv, .tsv, etc) for: (1) Creating new spreadsheets with formulas and formatting, (2) Reading or analyzing data, (3) Modify existing spreadsheets while preserving formulas, (4) Data analysis and visualization in spreadsheets, or (5) Recalculating formulas"
license: Proprietary. LICENSE.txt has complete terms
compatibility: Requires Python with `pandas` and `openpyxl`, and a LibreOffice install (`soffice` on PATH) for formula recalculation via `recalc.py`.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Create, edit, and analyze spreadsheet files (.xlsx, .xlsm, .csv, .tsv)
  with formulas, formatting, and data analysis. Emphasis on dynamic Excel
  formulas (never Python-hardcoded calculated values) and on shipping
  models with zero formula errors.

trigger_when:
  - Creating new spreadsheets with formulas and formatting.
  - Reading or analyzing data in a spreadsheet file.
  - Modifying an existing spreadsheet while preserving its formulas.
  - Performing data analysis or visualization inside a spreadsheet.
  - Recalculating formulas in an .xlsx file.
  - User mentions .xlsx, .xlsm, .csv, or .tsv files.

scope_and_approval: >
  Every Excel file delivered MUST have ZERO formula errors (#REF!,
  #DIV/0!, #VALUE!, #N/A, #NAME?). When updating an existing file, study
  and EXACTLY match its format, style, and conventions — existing template
  conventions ALWAYS override the defaults in this skill; do NOT impose
  standardized formatting on files with established patterns. LibreOffice
  is required for formula recalculation via `recalc.py`; assume it is
  installed (the script auto-configures the macro on first run).

steps:
  - name: choose-tool
    description: >
      Pick the library. Use pandas for data analysis, bulk operations, and
      simple data export. Use openpyxl for complex formatting, formulas,
      and Excel-specific features. The two often combine in one workflow.
      See modes `pandas-data-analysis` and `openpyxl-formulas-formatting`.
  - name: create-or-load
    description: >
      Create a new workbook with `openpyxl.Workbook()` or load an existing
      one with `load_workbook('file.xlsx')`. To read calculated values
      only, use `data_only=True` — but do NOT save the workbook back in
      that mode, or formulas will be permanently replaced with values.
  - name: modify
    description: >
      Add or edit data, formulas, and formatting. Use Excel formulas (NOT
      Python-calculated hardcoded values) for sums, percentages, ratios,
      differences, and similar derivations. For financial models, apply
      the rules in mode `financial-modeling-standards`.
  - name: save
    description: Write the workbook to file with `wb.save('output.xlsx')`.
    depends_on: [modify]
  - name: recalculate
    description: >
      MANDATORY when the file contains formulas. Run
      `python recalc.py <excel_file> [timeout_seconds]` from the skill
      root. The script auto-configures LibreOffice on first run,
      recalculates all formulas in all sheets, scans every cell for Excel
      errors, and prints a JSON report with `status`, `total_errors`,
      `total_formulas`, and `error_summary`.
    depends_on: [save]
  - name: verify-and-fix
    description: >
      Parse the JSON from `recalc.py`. If `status` is `errors_found`,
      inspect `error_summary` and resolve each error type per the
      `decisions` table. Re-run `recalc.py` until `status` is `success`.
      Also walk the `formula-verification-checklist` mode before declaring
      the model done.
    depends_on: [recalculate]

decisions:
  - signal: "`recalc.py` reports #REF!"
    action: Invalid cell reference. Verify references point to intended cells; check for ranges shifted by inserted or deleted rows/columns and for cross-sheet references that lost their sheet name.
  - signal: "`recalc.py` reports #DIV/0!"
    action: Division by zero. Guard the denominator with an `IF` check before dividing, or wrap the whole formula in `IFERROR(...)`.
  - signal: "`recalc.py` reports #VALUE!"
    action: Wrong data type in a formula. Confirm operands are numeric (or the expected type) and not stray text or blanks.
  - signal: "`recalc.py` reports #NAME?"
    action: Unrecognized formula name. Check spelling of function names and named ranges; confirm the function exists in target Excel.
  - signal: "`recalc.py` reports #N/A"
    action: Lookup with no match. Verify the lookup key exists in the range; use `IFERROR` or `IFNA` to handle expected misses.
  - signal: Updating an existing file that already has consistent formatting/conventions.
    action: Mirror the file's existing format, style, and color conventions exactly. Do NOT apply the defaults in `financial-modeling-standards`.

modes:
  - name: pandas-data-analysis
    body: |
      Use pandas for data analysis, visualization, and bulk operations.

      ```python
      import pandas as pd

      # Read Excel
      df = pd.read_excel('file.xlsx')                          # first sheet
      all_sheets = pd.read_excel('file.xlsx', sheet_name=None) # dict of sheets

      # Analyze
      df.head()       # preview
      df.info()       # column info
      df.describe()   # statistics

      # Write Excel
      df.to_excel('output.xlsx', index=False)
      ```

      Tips:
      - Specify dtypes to avoid inference issues: `dtype={'id': str}`.
      - For large files, read only the columns you need:
        `usecols=['A', 'C', 'E']`.
      - Parse dates explicitly: `parse_dates=['date_column']`.

  - name: openpyxl-formulas-formatting
    body: |
      Use openpyxl for formulas, formatting, and Excel-specific features.
      Cell indices are 1-based (row=1, column=1 is A1).

      Create a new workbook:
      ```python
      from openpyxl import Workbook
      from openpyxl.styles import Font, PatternFill, Alignment

      wb = Workbook()
      sheet = wb.active

      sheet['A1'] = 'Hello'
      sheet['B1'] = 'World'
      sheet.append(['Row', 'of', 'data'])

      sheet['B2'] = '=SUM(A1:A10)'

      sheet['A1'].font = Font(bold=True, color='FF0000')
      sheet['A1'].fill = PatternFill('solid', start_color='FFFF00')
      sheet['A1'].alignment = Alignment(horizontal='center')

      sheet.column_dimensions['A'].width = 20

      wb.save('output.xlsx')
      ```

      Edit an existing workbook (preserving formulas and formatting):
      ```python
      from openpyxl import load_workbook

      wb = load_workbook('existing.xlsx')
      sheet = wb.active                  # or wb['SheetName']

      for sheet_name in wb.sheetnames:
          sheet = wb[sheet_name]

      sheet['A1'] = 'New Value'
      sheet.insert_rows(2)
      sheet.delete_cols(3)

      new_sheet = wb.create_sheet('NewSheet')
      new_sheet['A1'] = 'Data'

      wb.save('modified.xlsx')
      ```

      Cautions:
      - `load_workbook('file.xlsx', data_only=True)` returns calculated
        values; saving back in that mode DESTROYS the formulas.
      - For very large files use `read_only=True` (reading) or
        `write_only=True` (writing).
      - openpyxl writes formulas as strings; values are NOT computed until
        `recalc.py` runs.

  - name: financial-modeling-standards
    body: |
      Defaults for financial models. Apply unless the user or an existing
      template specifies otherwise.

      Color coding (industry standard):
      - Blue text (RGB 0,0,255) — hardcoded inputs and scenario-change cells.
      - Black text (RGB 0,0,0) — ALL formulas and calculations.
      - Green text (RGB 0,128,0) — links to other sheets in the same workbook.
      - Red text (RGB 255,0,0) — external links to other files.
      - Yellow background (RGB 255,255,0) — key assumptions or cells needing attention.

      Number formatting:
      - Years as text strings ("2024", not "2,024").
      - Currency: `$#,##0`; always specify units in headers ("Revenue ($mm)").
      - Zeros display as `-` via a custom format like `"$#,##0;($#,##0);-"`,
        including for percentages.
      - Percentages: default `0.0%` (one decimal).
      - Multiples (EV/EBITDA, P/E): `0.0x`.
      - Negative numbers in parentheses, e.g. `(123)`, not `-123`.

      Formula construction:
      - Place ALL assumptions (growth rates, margins, multiples) in
        separate assumption cells; reference them from formulas instead of
        hardcoding. Example: `=B5*(1+$B$6)` instead of `=B5*1.05`.
      - Verify all cell references are correct.
      - Check for off-by-one errors in ranges.
      - Keep formulas consistent across all projection periods.
      - Test edge cases (zero, negative, very large values).
      - Watch for unintended circular references.

      Documentation for hardcoded values:
      - Comment the cell, or place a note in the adjacent cell at end of table.
      - Format: `Source: [System/Document], [Date], [Specific Reference], [URL if applicable]`.
      - Examples:
        - "Source: Company 10-K, FY2024, Page 45, Revenue Note, [SEC EDGAR URL]"
        - "Source: Company 10-Q, Q2 2025, Exhibit 99.1, [SEC EDGAR URL]"
        - "Source: Bloomberg Terminal, 8/15/2025, AAPL US Equity"
        - "Source: FactSet, 8/20/2025, Consensus Estimates Screen"

  - name: formula-verification-checklist
    body: |
      Walk this checklist before declaring a model done.

      Essential verification:
      - Test 2–3 sample formula references against expected values before
        applying the pattern broadly.
      - Confirm column letters match indexes (column 64 = BL, not BK).
      - Excel rows are 1-indexed (DataFrame row 5 = Excel row 6).

      Common pitfalls:
      - Handle NaNs with `pd.notna()`.
      - FY data often sits in far-right columns (50+).
      - When searching, look at ALL occurrences, not just the first.
      - Guard denominators before `/` to avoid `#DIV/0!`.
      - Verify all cell references to avoid `#REF!`.
      - Use `Sheet1!A1` format for cross-sheet references.

      Testing strategy:
      - Start small: test on 2–3 cells before broad application.
      - Verify that every cell referenced by a formula actually exists.
      - Include zero, negative, and very large values in edge-case tests.

      Interpreting `recalc.py` output:
      ```json
      {
        "status": "success",            // or "errors_found"
        "total_errors": 0,
        "total_formulas": 42,
        "error_summary": {
          "#REF!": {
            "count": 2,
            "locations": ["Sheet1!B5", "Sheet1!C10"]
          }
        }
      }
      ```

scenarios:
  - need: User wants the sum of B2:B9 to land in B10.
    context: Tempting to compute the sum in Python and write the number to B10.
    action: Write the formula `sheet['B10'] = '=SUM(B2:B9)'`.
    outcome: B10 recalculates when source data changes; satisfies the "no hardcoded calculated values" rule.
  - need: User wants a year-over-year revenue growth rate in C5.
    action: Write `sheet['C5'] = '=(C4-C2)/C2'` instead of computing the rate in Python and hardcoding the result.
    outcome: Cell updates automatically when revenue inputs change.
  - need: Average of D2:D19 in D20.
    action: Write `sheet['D20'] = '=AVERAGE(D2:D19)'`.
    outcome: Stays dynamic; no Python-side recompute needed when D2:D19 changes.
  - need: A new .xlsx with many formulas must be delivered error-free.
    action: After `wb.save(...)`, run `python recalc.py output.xlsx`, parse the JSON, fix each error in `error_summary` per the `decisions` table, and re-run until `status` is `success`.
    outcome: File ships with all formulas evaluated and zero error cells.

anti_patterns:
  - Hardcoding a value calculated in Python into a cell instead of writing the equivalent Excel formula. Spreadsheets must recalculate when source data changes.
  - Embedding hardcoded numbers directly in formulas (e.g. `=B5*1.05`) instead of referencing a named assumption cell (e.g. `=B5*(1+$B$6)`).
  - Loading a workbook with `data_only=True` and saving it back — this permanently replaces all formulas with their last calculated values.
  - Skipping `recalc.py` after writing formulas with openpyxl; openpyxl stores formulas as strings and does NOT compute their values.
  - Imposing the defaults in `financial-modeling-standards` on a file that already has consistent conventions of its own.
  - Writing Excel files without documenting the source of hardcoded values (system, date, specific reference, URL).
  - Writing verbose Python with unnecessary comments, long variable names, or stray print statements for Excel operations.
```
