# Spreadsheet guide (adapted from the curated `xlsx` skill)

Load this when you build or edit a workbook, when you need pandas or openpyxl reading tips, or when the task asks for a workbook deliverable.

## Reading and analysing data
- pandas for analysis: `pd.read_excel(path, sheet_name=None)` returns every sheet as a dict. Then use `df.head()`, `df.info()`, `df.describe()`.
- Case-study sheets have titles above the table. Pass `header=<0-based header row>` and `usecols="C:J"` (or similar), or read cell by cell with openpyxl. Excel rows are 1-indexed: DataFrame row 5 is Excel row 6 under a header in row 1.
- Specify dtypes to avoid inference issues: `dtype={'id': str}`. Read only the columns you need with `usecols=[...]`. Parse dates with `parse_dates=[...]`.
- Check for nulls with `pd.notna()`. Blank rows inside a block can be holes left by displaced records. Search for every match, not just the first. FY data often sits in far-right columns (50+). Confirm column letters: column 64 is BL, not BK.
- openpyxl: cells are 1-based (row=1, column=1 is A1). `data_only=True` reads cached values. Saving a workbook opened with `data_only=True` replaces its formulas with values and loses them for good. Use `read_only=True` for big reads and `write_only=True` for big writes.

## Deliverable workbooks
- **Zero formula errors**: no #REF!, #DIV/0!, #VALUE!, #N/A, #NAME?.
- **Preserve templates**: study and EXACTLY match the existing format, style, and conventions. Never impose standard formatting on a file with established patterns. Existing template conventions always override the rules below.
- **Use formulas, not hardcoded Python results**: write `sheet['B10'] = '=SUM(B2:B9)'`, not the computed total. This applies to totals, percentages, ratios, differences, and averages, so the sheet recalculates when the inputs change.
- **Assumptions** go in their own cells, referenced absolutely: `=B5*(1+$B$6)`, not `=B5*1.05`.
- **Colour coding** (unless the user or the template says otherwise): blue text 0,0,255 for hardcoded inputs and scenario numbers; black text for ALL formulas and calculations; green text 0,128,0 for links to other sheets in the same workbook; red text 255,0,0 for links to other files; yellow fill 255,255,0 for key assumptions or cells that need updating.
- **Number formats**: years as text ("2024", not "2,024"). Currency as `$#,##0` with units in the header ("Revenue ($mm)"). Zeros shown as "-", e.g. `$#,##0;($#,##0);-`. Percentages as 0.0%. Multiples as 0.0x. Negatives in parentheses: (123).
- **Document hardcodes** in a cell comment or an adjacent cell: "Source: [System/Document], [Date], [Specific Reference], [URL if applicable]", e.g. "Source: Company 10-K, FY2024, Page 45, Revenue Note, [SEC EDGAR URL]". Comment complex formulas and key assumptions, and add notes on the main calculations and model sections.
- **Formula checks**: test 2-3 references before building out the model. Watch for off-by-one ranges. Keep formulas consistent across periods. Test zero, negative, and very large values. Avoid unintended circular references. Use `Sheet1!A1` for cross-sheet references. Guard denominators against #DIV/0!.
- **Workflow**: pick the tool (pandas for data, openpyxl for formulas and formatting), create or load, modify, save, recalculate, then fix errors and recalculate again.
- **Create / edit with openpyxl**:
  ```python
  from openpyxl import Workbook, load_workbook
  from openpyxl.styles import Font, PatternFill, Alignment
  wb = Workbook(); sh = wb.active                       # or load_workbook('existing.xlsx'); sh = wb['Data']
  sh['A1'] = 'Label'; sh.append(['Row', 'of', 'data']); sh['B2'] = '=SUM(A1:A10)'
  sh['A1'].font = Font(bold=True, color='0000FF')       # blue = input
  sh['A1'].fill = PatternFill('solid', start_color='FFFF00')
  sh['A1'].alignment = Alignment(horizontal='center')
  sh.column_dimensions['A'].width = 20
  sh.insert_rows(2); sh.delete_cols(3); wb.create_sheet('Model')
  wb.save('output.xlsx')                                 # pandas export: df.to_excel('out.xlsx', index=False)
  ```
- **Recalculate**: openpyxl writes formulas without values. Run `python scripts/recalc.py <file.xlsx> [timeout_s]`. It sets up a LibreOffice macro on first run, recalculates every sheet, scans every cell for errors, and returns JSON: `status` (`success` or `errors_found`), `total_errors`, `total_formulas`, and `error_summary` (error type to `count` and `locations`). Fix #REF! (bad references), #DIV/0!, #VALUE! (wrong types), and #NAME? (unknown functions), then rerun. **The task container has no LibreOffice (`soffice`)**. When it is missing, check the same logic by recomputing it in pandas and comparing, and say that the workbook was not recalculated.
- Code style: keep the Python minimal, with no needless comments, verbose names, or prints.
