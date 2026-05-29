---
name: xlsx
description: "Comprehensive spreadsheet creation, editing, and analysis with support for formulas, formatting, data analysis, and visualization. Use when working with spreadsheets (.xlsx, .xlsm, .csv, .tsv, etc) for: (1) Creating new spreadsheets with formulas and formatting, (2) Reading or analyzing data, (3) Modifying existing spreadsheets while preserving formulas, (4) Data analysis and visualization in spreadsheets, or (5) Recalculating formulas."
license: Proprietary. LICENSE.txt has complete terms
compatibility: Requires Python with pandas and openpyxl. Formula recalculation requires LibreOffice (soffice) on PATH; the recalc script auto-configures the LibreOffice macro on first run. Works on Linux and macOS.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Create, edit, and analyze .xlsx (and related .xlsm/.csv/.tsv) spreadsheets
  using pandas for data work and openpyxl for formulas/formatting. Every
  delivered workbook must contain ZERO formula errors (#REF!, #DIV/0!,
  #VALUE!, #N/A, #NAME?, #NULL!, #NUM!). Calculations must live in Excel
  formulas, not as Python-computed hardcoded values, so the workbook stays
  dynamic. When the deliverable is a financial model, apply industry-standard
  color/number conventions unless an existing template overrides them.

trigger_when:
  - User asks to create a new spreadsheet (.xlsx, .xlsm) with data, formulas, or formatting.
  - User asks to read, summarize, or analyze data in a spreadsheet or CSV/TSV.
  - User asks to modify an existing spreadsheet while preserving its formulas and styles.
  - User asks for data analysis or visualization that should be delivered as a spreadsheet.
  - A workbook contains formulas authored via openpyxl and needs recalculation before delivery.
  - User mentions financial models, projections, assumptions, or sources that should be cited in cells.

do_not_use_when:
  - The deliverable is a non-spreadsheet document (PDF, Word, Markdown report) that happens to mention numbers.
  - The task is purely tabular printing to stdout with no expectation of a saved .xlsx file.
  - The user explicitly asks for a Google Sheets / gspread workflow rather than a local .xlsx.

scope_and_approval: >
  Read, create, and modify workbooks under the working directory freely. When
  editing a workbook the user already produced, study and EXACTLY match its
  existing format, style, and conventions before changing anything — existing
  template conventions ALWAYS override the financial-model defaults in this
  skill. Do not impose standardized formatting on workbooks with established
  patterns. Loading a workbook with `data_only=True` and saving over it
  permanently destroys formulas — never do this on a user-owned file.

steps:
  - name: classify-task
    description: >
      Decide what the user is asking for: (a) read/analyze, (b) create new,
      (c) edit existing, (d) recalculate formulas. Also decide whether the
      deliverable is a financial model (projections, valuation, assumptions
      that need the industry color/number conventions) or a general-purpose
      workbook. Carry the answers into later steps so library choice and
      convention application match the task.
    outputs:
      - name: task-kind
        type: string
        description: One of `analyze`, `create`, `edit`, `recalc-only`.
      - name: is-financial-model
        type: boolean
        description: True if the workbook is a financial model and the color/number conventions in `apply-financial-conventions` apply.
      - name: target-path
        type: string
        description: Path to the input or output workbook.

  - name: choose-library
    description: >
      pandas is best for data analysis, bulk operations, and simple data
      export. openpyxl is best for complex formatting, formulas, and
      Excel-specific features. For an analyze-only task on existing data,
      pandas usually suffices. For any task that writes formulas, applies
      cell formatting, preserves an existing template, or sets column widths,
      use openpyxl. A workflow may combine both: pandas to inspect, openpyxl
      to write.
    inputs:
      - name: task-kind
        type: string
      - name: is-financial-model
        type: boolean
    outputs:
      - name: library-choice
        type: string
        description: '`pandas`, `openpyxl`, or `both`.'

  - name: load-or-create-workbook
    description: |
      Load or create the workbook with the chosen library.

      pandas (read):

          import pandas as pd
          df = pd.read_excel('file.xlsx')                       # default first sheet
          all_sheets = pd.read_excel('file.xlsx', sheet_name=None)  # dict of sheets

      pandas read tips: pass `dtype={'id': str}` to avoid inference issues,
      `usecols=[...]` for large files, `parse_dates=['date_column']` for dates.

      openpyxl (create new):

          from openpyxl import Workbook
          from openpyxl.styles import Font, PatternFill, Alignment
          wb = Workbook()
          sheet = wb.active

      openpyxl (load existing — preserves formulas and formatting):

          from openpyxl import load_workbook
          wb = load_workbook('existing.xlsx')
          sheet = wb.active  # or wb['SheetName']
          for sheet_name in wb.sheetnames:
              sheet = wb[sheet_name]

      openpyxl notes: cell indices are 1-based (row=1, column=1 → A1). For
      large files use `read_only=True` to read or `write_only=True` to write.
      To READ calculated values use `load_workbook('file.xlsx', data_only=True)`
      — but if you then save that workbook, formulas are replaced by values
      and permanently lost.
    inputs:
      - name: library-choice
        type: string
      - name: target-path
        type: string
    outputs:
      - name: workbook
        type: object
        description: Live pandas DataFrame(s) or openpyxl Workbook object.

  - name: analyze-data
    description: |
      Optional — only when `task-kind` is `analyze` or the workflow needs an
      analysis pass before writing. Use pandas:

          df.head()       # preview rows
          df.info()       # column dtypes, null counts
          df.describe()   # summary statistics

      For multi-sheet inspection iterate the dict returned by
      `pd.read_excel('file.xlsx', sheet_name=None)`.

      Watch for: NaN handling (`pd.notna()`), far-right FY columns (often in
      columns 50+), and multiple matches when searching (search ALL
      occurrences, not just the first).
    depends_on: [load-or-create-workbook]
    inputs:
      - name: workbook
        type: object

  - name: apply-content-and-formulas
    description: |
      Populate cells, formulas, and basic styles via openpyxl.

      CRITICAL: Use Excel formulas, NOT Python-computed hardcoded values.
      Hardcoding calculated results in cells breaks the dynamic recalculation
      contract — when source data changes, a hardcoded total cannot update.

      ❌ WRONG — hardcoding a Python-computed value:

          total = df['Sales'].sum()
          sheet['B10'] = total                              # hardcodes 5000
          growth = (df.iloc[-1]['Revenue'] - df.iloc[0]['Revenue']) / df.iloc[0]['Revenue']
          sheet['C5'] = growth                              # hardcodes 0.15
          avg = sum(values) / len(values)
          sheet['D20'] = avg                                # hardcodes 42.5

      ✅ CORRECT — Excel formula strings that Excel evaluates:

          sheet['B10'] = '=SUM(B2:B9)'
          sheet['C5']  = '=(C4-C2)/C2'
          sheet['D20'] = '=AVERAGE(D2:D19)'

      Applies to ALL calculations — totals, percentages, ratios, differences.

      Cell, row, and sheet edits:

          sheet['A1'] = 'Hello'
          sheet.append(['Row', 'of', 'data'])
          sheet.insert_rows(2)
          sheet.delete_cols(3)
          new_sheet = wb.create_sheet('NewSheet')

      Styling and column widths:

          sheet['A1'].font = Font(bold=True, color='FF0000')
          sheet['A1'].fill = PatternFill('solid', start_color='FFFF00')
          sheet['A1'].alignment = Alignment(horizontal='center')
          sheet.column_dimensions['A'].width = 20

      Place ALL assumptions (growth rates, margins, multiples) in separate
      assumption cells and reference them, e.g. `=B5*(1+$B$6)` not `=B5*1.05`.

      For cross-sheet links use `Sheet1!A1` syntax.
    depends_on: [load-or-create-workbook]
    inputs:
      - name: workbook
        type: object

  - name: apply-financial-conventions
    description: |
      Apply ONLY when `is-financial-model` is true AND there is no existing
      template whose conventions take precedence. When editing a file with
      established patterns, match those patterns instead.

      Color coding (industry standard):
        - Blue text  (RGB 0,0,255):   Hardcoded inputs and scenario numbers.
        - Black text (RGB 0,0,0):     ALL formulas and calculations.
        - Green text (RGB 0,128,0):   Links pulling from other worksheets in the same workbook.
        - Red text   (RGB 255,0,0):   External links to other files.
        - Yellow fill (RGB 255,255,0): Key assumptions needing attention or cells to update.

      Number formatting:
        - Years: text strings ("2024" not "2,024").
        - Currency: `$#,##0` format; ALWAYS state units in headers (e.g. "Revenue ($mm)").
        - Zeros: use number formatting to render zeros as "-", including percentages,
          e.g. `"$#,##0;($#,##0);-"`.
        - Percentages: default `0.0%` (one decimal).
        - Multiples: `0.0x` for valuation multiples (EV/EBITDA, P/E).
        - Negatives: parentheses `(123)`, not `-123`.

      Hardcode documentation: every hardcoded input cell gets a comment (or a
      neighbouring cell if the table edge is right there) of the form
      `Source: [System/Document], [Date], [Specific Reference], [URL if applicable]`.
      Examples:
        - `Source: Company 10-K, FY2024, Page 45, Revenue Note, [SEC EDGAR URL]`
        - `Source: Company 10-Q, Q2 2025, Exhibit 99.1, [SEC EDGAR URL]`
        - `Source: Bloomberg Terminal, 8/15/2025, AAPL US Equity`
        - `Source: FactSet, 8/20/2025, Consensus Estimates Screen`
    depends_on: [apply-content-and-formulas]
    inputs:
      - name: is-financial-model
        type: boolean
      - name: workbook
        type: object

  - name: save-workbook
    description: |
      pandas:

          df.to_excel('output.xlsx', index=False)

      openpyxl:

          wb.save('output.xlsx')
    depends_on: [apply-content-and-formulas]
    inputs:
      - name: workbook
        type: object
      - name: target-path
        type: string
    outputs:
      - name: saved-path
        type: string

  - name: recalculate-formulas
    description: >
      MANDATORY whenever the workbook contains any formulas authored via
      openpyxl. openpyxl writes formulas as strings without evaluating them;
      until recalculation runs, cached cell values are stale or missing. The
      script auto-configures a LibreOffice headless macro on first run,
      recalculates every formula in every sheet, scans ALL cells for Excel
      error sigils, and returns a JSON report. Skip ONLY for pandas-only or
      analyze-only flows that wrote no formulas.
    script: scripts/recalc.py
    depends_on: [save-workbook]
    inputs:
      - name: saved-path
        type: string
    outputs:
      - name: recalc-report
        type: object
        description: |
          JSON shape:
            {
              "status": "success" | "errors_found",
              "total_errors": <int>,
              "total_formulas": <int>,
              "error_summary": {
                "#REF!":   {"count": <int>, "locations": ["Sheet1!B5", ...]},
                "#DIV/0!": {...},
                ...
              }
            }
          Up to 20 locations are listed per error type.

  - name: verify-and-fix-errors
    description: |
      Read the recalc report. If `status` is `success` and `total_errors` is
      0, proceed to `final-verification`. Otherwise inspect `error_summary`
      and fix each kind:
        - `#REF!`:   invalid cell references — verify ranges and sheet names.
        - `#DIV/0!`: division by zero — guard denominators (e.g. `IFERROR`, `IF(B2=0,0,A2/B2)`).
        - `#VALUE!`: wrong data type in a formula — check that text is not being multiplied, etc.
        - `#NAME?`:  unrecognized formula name — fix the spelling or function name.
        - `#NULL!`, `#NUM!`, `#N/A`: review per Excel docs; usually bad ranges, out-of-domain math, or missing lookups.
      Re-save and re-run `recalculate-formulas`. Loop until zero errors.
      Zero formula errors is the delivery contract.
    depends_on: [recalculate-formulas]
    inputs:
      - name: recalc-report
        type: object

  - name: final-verification
    description: |
      Walk this checklist before declaring the workbook done:

      Essential:
        - Tested 2–3 sample references and confirmed they pull the correct values.
        - Excel column letters match the integer indices (column 64 = BL, not BK).
        - Excel rows are 1-indexed (DataFrame row 5 = Excel row 6).

      Formula correctness:
        - All cell references point to the intended cells (no leftover #REF!).
        - Denominators in `/` formulas are guarded against zero.
        - Cross-sheet references use `Sheet1!A1` form, not bare `A1`.
        - Formulas are consistent across all projection periods (no off-by-one in copied ranges).
        - No unintended circular references.
        - Edge cases tested: zero, negative, and very large values where applicable.

      Conventions (financial models only):
        - Color coding applied per `apply-financial-conventions`.
        - Number formats applied; zeros render as "-".
        - Hardcoded inputs have Source comments in the prescribed format.

      If any check fails, return to the relevant earlier step and re-run
      `recalculate-formulas` before re-checking.
    depends_on: [verify-and-fix-errors]

search_shortcuts:
  - category: Library selection
    body: |
      - pandas — data analysis, bulk operations, simple data export.
      - openpyxl — formulas, formatting, multi-sheet structure, column widths, styles.
      - Combine: pandas for inspection, openpyxl for the deliverable when formulas/formatting matter.
  - category: openpyxl essentials
    body: |
      - Cell indices are 1-based.
      - `load_workbook('file.xlsx', data_only=True)` exposes cached calculated values; saving over the file after this DESTROYS the formulas.
      - `read_only=True` / `write_only=True` for large files.
      - Cross-sheet reference syntax: `Sheet1!A1`.
  - category: pandas essentials
    body: |
      - `pd.read_excel('file.xlsx', sheet_name=None)` returns a dict of every sheet.
      - `dtype={'id': str}` prevents type inference surprises.
      - `usecols=[...]` and `parse_dates=[...]` keep large reads cheap and correct.
  - category: Recalculation
    body: |
      - `python scripts/recalc.py <excel_file> [timeout_seconds]` — JSON to stdout.
      - Requires `soffice` on PATH; macro is installed on first run.

scenarios:
  - need: Build a new revenue projection model from raw data.
    context: User provides a CSV of monthly sales; wants a 5-year projection workbook with assumptions.
    action: pandas reads the CSV; openpyxl writes the model with `=SUM(...)`, `=B5*(1+$B$6)`, and per-period formulas. Financial conventions applied (blue inputs, black formulas, yellow assumption fills, currency format with units in headers). Save, recalc, verify zero errors.
    outcome: Delivered .xlsx with all calculations as live formulas, assumptions cells highlighted, sources cited next to each hardcoded input.

  - need: Add a Q3 column to an existing financial model.
    context: Loaded `model.xlsx` and observed it already uses different color codes than the defaults in this skill.
    action: Followed the existing template's conventions (NOT the defaults). Copied the formula pattern from Q2 across, kept the styling consistent. Save, recalc, verify.
    outcome: New column matches existing patterns; zero formula errors.

  - need: Analyze a workbook to find which sheets contain FY2025 data.
    context: 12-sheet workbook; user wants a summary, not a new file.
    action: Used `pd.read_excel(..., sheet_name=None)`; iterated sheets, used `pd.notna()` to filter, searched ALL columns including far-right (50+) for FY2025 markers, listed every match (not just the first).
    outcome: Returned a sheet-by-sheet report of FY2025 column locations. No file written, no recalc needed.

  - need: A delivered model is showing `#DIV/0!` in three cells.
    context: 'recalc.py reported error_summary with #DIV/0! at count 3 and locations Sheet1!E14, Sheet1!F14, Sheet1!G14.'
    action: Opened those cells, found denominators that are zero in early years. Wrapped each in `IFERROR(.../denom, 0)` or `IF(denom=0, 0, num/denom)`. Re-saved, re-ran recalc.
    outcome: 'Recalc report shows total_errors of 0. Model delivered.'

anti_patterns:
  - Calculating a value in Python and writing the result to a cell — breaks dynamic recalculation. Write the Excel formula string instead.
  - Skipping `recalc.py` after writing formulas with openpyxl — cached values are missing or stale, and Excel error sigils go undetected.
  - Opening a user-owned workbook with `data_only=True` and saving over it — formulas are permanently replaced by cached values.
  - Applying this skill's default color/number conventions to a workbook that already has its own established conventions. Match the existing template instead.
  - Hardcoding scenario inputs inside formulas (`=B5*1.05`) instead of placing the assumption in its own cell and referencing it (`=B5*(1+$B$6)`).
  - Writing hardcoded inputs to a financial model without a Source comment (or adjacent cell) in the prescribed format.
  - Stopping at "the script ran without errors" instead of checking `total_errors == 0` in the recalc report.
  - Writing verbose Python — long variable names, narrative print statements, comments describing what obvious code does. Keep generation lean.
  - Searching only the first match when scanning multi-sheet workbooks for a term. Search ALL occurrences.
```
