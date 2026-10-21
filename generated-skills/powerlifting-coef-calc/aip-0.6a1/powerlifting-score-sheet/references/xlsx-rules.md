# Excel workbook rules (from the xlsx skill)

## Requirements for every workbook

- Zero formula errors: no #REF!, #DIV/0!, #VALUE!, #N/A, #NAME? (also check #NULL!, #NUM!).
- Preserve existing templates: match the file's existing format, style and conventions; never
  impose standard formatting on a file with an established pattern.
- Use Excel formulas, not values computed in Python and hardcoded, for every calculation
  (totals, ratios, coefficients) so the sheet recalculates when the data changes.
  Wrong: `ws["G2"] = 610.0`. Right: `ws["G2"] = "=SUM(D2,E2,F2)"`.
- Put assumptions in cells and reference them rather than burying constants, when building a
  model; document the source of any hardcoded number in a cell comment or adjacent cell
  ("Source: <system/document>, <date>, <reference>, <URL>").

Financial-model conventions (apply only to financial models, unless the file already uses them):
blue text = hardcoded inputs, black = formulas, green = links to other sheets, red = external
links, yellow fill = key assumptions; years as text; currency `$#,##0` with units in headers;
zeros shown as `-`; percentages `0.0%`; multiples `0.0x`; negatives in parentheses.

## Tools

- pandas for reading/analysis (`pd.read_excel(path, sheet_name=None)` loads all sheets;
  `dtype=`, `usecols=`, `parse_dates=` to control inference); openpyxl for formulas and formatting.
- openpyxl cells are 1-based. `load_workbook(path, data_only=True)` reads cached values; saving a
  workbook opened that way replaces every formula with its value permanently — never save it.
- `read_only=True` / `write_only=True` for large files.
- openpyxl writes formulas without values. Recalculate before anyone reads values.

## Recalculating: `scripts/recalc.py`

    python scripts/recalc.py <excel_file> [timeout_seconds]   # default 30

Needs LibreOffice (`soffice`); it installs a `RecalculateAndSave` macro in the LibreOffice user
profile on first run, recalculates every sheet in place, scans every cell for errors and prints:

    {"status": "success" | "errors_found", "total_errors": 0, "total_formulas": 42,
     "error_summary": {"#REF!": {"count": 2, "locations": ["Sheet1!B5", "Sheet1!C10"]}}}

On `errors_found`, fix the listed cells and recalculate again. Typical causes: #REF! invalid
reference, #DIV/0! zero denominator, #VALUE! text where a number is expected, #NAME? unknown
function. Alternatives when the macro fails: `soffice --headless --convert-to xlsx --outdir <dir>
<file>` (then copy the converted file back) or gnumeric `ssconvert --recalc <in> <out>`.

## Verification checklist

- Test 2-3 sample references before filling every row; confirm column letters (column 64 = BL).
- Excel rows are 1-based and row 1 is the header: DataFrame row 5 is Excel row 6.
- Blank cells: check with `pd.notna()`; guard denominators; test zero, negative, large values.
- Cross-sheet references use `Sheet!A1`; avoid circular references.
- Code style: concise Python, no needless prints; comment complex formulas in the workbook.
