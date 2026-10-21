# Spreadsheet guidelines (from the xlsx skill)

Read this when you go beyond what `scripts/score_sheet.py` does: adding extra sheets,
summaries, formatting, or editing the workbook by hand.

## Requirements for every workbook
- Deliver with zero formula errors (#REF!, #DIV/0!, #VALUE!, #N/A, #NAME?).
- Preserve existing templates: study and exactly match the existing format, style, and
  conventions. Existing conventions override everything below.
- Use Excel formulas, never values computed in Python and pasted in, for every derived
  number (totals, ratios, coefficients) so the sheet recalculates when data changes.
  Wrong: `sheet['B10'] = df['Sales'].sum()`. Right: `sheet['B10'] = '=SUM(B2:B9)'`.
- Put assumptions (constants such as rates) in their own cells and reference them
  (`=B5*(1+$B$6)`, not `=B5*1.05`) — unless the task fixes the column layout, as the
  score task does; then keep constants inside the formula.
- Document hardcoded sources in a cell comment or adjacent cell:
  "Source: [System/Document], [Date], [Specific Reference], [URL if applicable]".
- Add comments to cells with complex formulas or important assumptions only where it
  does not alter a layout the task specifies.

## Financial models only (unless the user/template says otherwise)
- Font colors: blue (0,0,255) hardcoded inputs; black (0,0,0) formulas; green (0,128,0)
  links to other sheets in the same workbook; red (255,0,0) links to other files;
  yellow fill (255,255,0) key assumptions / cells to update.
- Number formats: years as text ("2024"); currency `$#,##0` with units in the header
  ("Revenue ($mm)"); zeros shown as "-" (`$#,##0;($#,##0);-`); percentages `0.0%`;
  multiples `0.0x`; negatives in parentheses.
- Formula hygiene: verify references, check off-by-one ranges, consistent formulas across
  periods, test edge cases (zero, negative), no unintended circular references.

## Tools
- pandas for analysis (`pd.read_excel(path, sheet_name=None)`, `dtype=`, `usecols=`,
  `parse_dates=`); openpyxl for formulas and formatting.
- openpyxl: cells are 1-based; DataFrame row 5 = Excel row 6; column 64 = BL.
  `load_workbook(path, data_only=True)` reads cached values — never save a workbook opened
  that way (formulas are lost). `read_only=True` / `write_only=True` for large files.
  openpyxl writes formulas without values; run `python scripts/recalc.py <file> [timeout]`.
- recalc.py output: `{"status": "success"|"errors_found", "total_errors", "total_formulas",
  "error_summary": {"#REF!": {"count", "locations"}}}` or `{"error": "..."}`.
  Fixes: #REF! invalid reference; #DIV/0! check denominators; #VALUE! wrong data type;
  #NAME? unrecognized function name.
- Verification checklist: test 2–3 sample references before building everything; handle
  NaN with `pd.notna()`; search all matches, not just the first; cross-sheet refs use
  `Sheet1!A1`; start formulas on a few cells before applying broadly.
- Code style: minimal, concise Python; no unnecessary comments or prints.
