# Spreadsheet rules (from the xlsx skill)

Load when editing a workbook by hand (manual-score, repairs) or when explaining why the sheet is built the way it is.

## Requirements for outputs
- Zero formula errors: no `#REF!`, `#DIV/0!`, `#VALUE!`, `#N/A`, `#NAME?` (also `#NULL!`, `#NUM!`).
- Preserve existing templates: study and exactly match the workbook's format, style, and conventions; never impose standard formatting on a file with established patterns. Existing conventions override every guideline below.
- Use formulas, not hardcoded values: compute totals, ratios and scores as Excel formulas (`=SUM(D2:F2)`), never as numbers calculated in Python and pasted in. The sheet must recalculate when the source data changes.

## Tools
- pandas for analysis and bulk reads (`pd.read_excel(path, sheet_name=None)` for all sheets; `dtype=`, `usecols=` for control). openpyxl for formulas, formatting and editing existing files.
- openpyxl cells are 1-based (row=1, column=1 is A1). DataFrame row 5 = Excel row 6 (header row). Confirm column letters (column 64 = BL).
- `load_workbook(path, data_only=True)` reads cached values; saving a workbook opened that way replaces every formula with its value permanently. Open twice (once with, once without) when you need both.
- openpyxl writes formulas without values. Recalculate with LibreOffice: `python scripts/recalc.py <file> [timeout_seconds]` (sets up the LibreOffice macro on first run, recalculates every sheet, scans every cell). Output JSON: `status` `success` or `errors_found`, `total_errors`, `total_formulas`, `error_summary` by error type with up to 20 locations. Fix and rerun until `success`.
- Container note: `pip install openpyxl` is present; pandas is not guaranteed. LibreOffice (`soffice`) and gnumeric are installed there.

## Formula verification checklist
- Test 2-3 sample references before filling a whole column; check off-by-one ranges and that every referenced cell exists.
- NaN/blank handling: a reference to an empty cell evaluates to 0; guard divisions (`#DIV/0!`).
- Cross-sheet references: `Sheet1!A1`, quoted when the name has spaces: `'My Data'!A1`.
- Test edge cases: zero, negative and very large values; no circular references.

## Financial-model conventions (only when the task is a financial model or asks for them)
Blue text inputs, black formulas, green cross-sheet links, red external links, yellow fill for key assumptions; assumptions in their own cells; years as text; currency `$#,##0` with units in headers; zeros shown as `-`; percentages `0.0%`; multiples `0.0x`; negatives in parentheses; document hardcoded sources ("Source: System, Date, Reference, URL"). A scoring sheet with a fixed layout from the task is not a financial model: do not add colour coding or assumption blocks to it.

## Code style
Write minimal, concise Python for workbook edits: no unnecessary comments, verbose names, or print statements. In the workbook itself, comment cells with complex formulas or important assumptions only when it does not change the requested layout.
