# XLSX working rules (adapted from the source `xlsx` skill)

Load when repairing a workbook by hand, when a task asks for spreadsheet work beyond the template (new sheets, formatting, a model), or to interpret `recalc.py` output.

## Requirements for every Excel output
- Zero formula errors: no #REF!, #DIV/0!, #VALUE!, #N/A, #NAME? anywhere in the delivered file.
- Preserve existing templates: study and exactly match the existing format, style and conventions; never impose standardized formatting on a file with established patterns. Template conventions always override the guidelines below.

## Use formulas, not hardcoded values
Always write Excel formulas instead of computing in Python and pasting the result, so the sheet recalculates when the source data changes. This covers totals, means, SDs, ratios, differences, percentages, rankings.
- Wrong: `sheet['B10'] = total` (a Python sum). Right: `sheet['B10'] = '=SUM(B2:B9)'`.
- Wrong: a Python growth rate or average pasted in. Right: `'=(C4-C2)/C2'`, `'=AVERAGE(D2:D19)'`.
- Put assumptions in their own cells and reference them (`=B5*(1+$B$6)`, not `=B5*1.05`).

## Workflow
1. Choose the tool: openpyxl for formulas and formatting. The task container has openpyxl 3.1.5 but **no pandas**; pandas (`pd.read_excel`, `df.describe()`, `sheet_name=None` for all sheets, `dtype=`, `usecols=`, `parse_dates=`) is only an option where it is installed.
2. Load (`load_workbook(path)`) or create (`Workbook()`); work on `wb[sheet_name]`; `insert_rows`, `delete_cols`, `create_sheet` as needed.
3. Write data, formulas and formatting (`Font`, `PatternFill('solid', start_color=...)`, `Alignment`, `column_dimensions[...].width`).
4. Save.
5. Recalculate (mandatory when formulas were written): `python3 scripts/recalc.py <file.xlsx> [timeout_seconds]`. It sets up a LibreOffice macro on first run, recalculates every sheet, saves, then scans every cell for errors.
6. Read its JSON. If `status` is `errors_found`, fix the cells listed in `error_summary` and recalculate again.

recalc.py output:
```
status: success | errors_found;  total_errors;  total_formulas;
error_summary: { "#REF!": { count, locations: ["Sheet1!B5", ...] } }   (only when errors exist; up to 20 locations each)
```
`{"error": ...}` means LibreOffice or the macro could not run.

## openpyxl facts
- Rows and columns are 1-based (row=1, column=1 is A1). DataFrame row 5 is Excel row 6 when there is a header.
- `load_workbook(path, data_only=True)` reads cached values; **saving a workbook opened that way replaces every formula with its value permanently.** Read values from a separate data_only load; edit and save a normal load.
- openpyxl writes formulas but never evaluates them; cached values exist only after recalc.
- Large files: `read_only=True` for reading, `write_only=True` for writing.
- Modern function names need their `_xlfn.` prefix in the file (`_xlfn.STDEV.S`); without it Excel shows #NAME?. Prefer the legacy equivalents (STDEV, STDEVP, VAR) which need none.

## Formula verification checklist
- Test 2–3 sample references against the source before filling a whole block.
- Column mapping: confirm letters (column 64 is BL, not BK); far-right data columns are easy to miss.
- Row offsets and off-by-one range ends.
- NaN/blank handling: INDEX/MATCH on a blank source cell returns 0, not blank; guard it.
- Multiple matches: MATCH returns the first; check IDs are unique.
- Division by zero: guard denominators (#DIV/0!), including SD of fewer than 2 values.
- Cross-sheet references: `'Sheet Name'!A1`; quote sheet names.
- Consistent formulas across every row/column of a block; no unintended circular references.
- Test edge cases: zero, negative, very large values, all-blank groups.

## Financial-model conventions (only when building a financial model and no template says otherwise)
- Text colours: blue (0,0,255) hardcoded inputs; black (0,0,0) formulas; green (0,128,0) links to other sheets in the workbook; red (255,0,0) links to other files. Yellow fill (255,255,0): key assumptions or cells to update.
- Number formats: years as text ("2024"); currency `$#,##0` with units in headers ("Revenue ($mm)"); zeros shown as "-" (`$#,##0;($#,##0);-`); percentages `0.0%`; multiples `0.0x`; negatives in parentheses.
- Document hardcodes in a comment or adjacent cell: "Source: [System/Document], [Date], [Specific Reference], [URL if applicable]".

## Style
- Python for spreadsheet work: minimal and concise, no needless comments, verbose names or prints.
- In the workbook: comment cells with complex formulas or key assumptions; document sources of hardcoded values; note key calculations and sections.
