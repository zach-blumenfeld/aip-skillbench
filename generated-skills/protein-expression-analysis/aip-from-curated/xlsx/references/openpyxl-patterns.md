# openpyxl patterns

Use openpyxl when the task touches formulas, cell styles, fonts, fills, comments, column widths, multiple sheets, or anything Excel-specific that pandas would discard.

## Creating a new workbook

```python
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

wb = Workbook()
sheet = wb.active

# Data
sheet['A1'] = 'Hello'
sheet['B1'] = 'World'
sheet.append(['Row', 'of', 'data'])

# Formula
sheet['B2'] = '=SUM(A1:A10)'

# Formatting
sheet['A1'].font = Font(bold=True, color='FF0000')
sheet['A1'].fill = PatternFill('solid', start_color='FFFF00')
sheet['A1'].alignment = Alignment(horizontal='center')

# Column width
sheet.column_dimensions['A'].width = 20

wb.save('output.xlsx')
```

## Editing an existing workbook

```python
from openpyxl import load_workbook

wb = load_workbook('existing.xlsx')
sheet = wb.active                    # or wb['SheetName']

for sheet_name in wb.sheetnames:
    sheet = wb[sheet_name]
    # ...

sheet['A1'] = 'New Value'
sheet.insert_rows(2)
sheet.delete_cols(3)

new_sheet = wb.create_sheet('NewSheet')
new_sheet['A1'] = 'Data'

wb.save('modified.xlsx')
```

## Use Excel formulas, never hardcoded computed values

The workbook must stay dynamic. Let Excel compute totals, percentages, ratios, growth rates, and differences — do not compute them in Python and write the result.

**Wrong**
```python
total = df['Sales'].sum()
sheet['B10'] = total                                 # hardcodes 5000

growth = (df.iloc[-1]['Revenue'] - df.iloc[0]['Revenue']) / df.iloc[0]['Revenue']
sheet['C5'] = growth                                  # hardcodes 0.15

avg = sum(values) / len(values)
sheet['D20'] = avg                                    # hardcodes 42.5
```

**Right**
```python
sheet['B10'] = '=SUM(B2:B9)'
sheet['C5']  = '=(C4-C2)/C2'
sheet['D20'] = '=AVERAGE(D2:D19)'
```

## Pitfalls

- **`data_only=True` is destructive.** `load_workbook('file.xlsx', data_only=True)` returns cached calculated values instead of formulas; saving that workbook silently replaces every formula with its last calculated value. Only use it for read-only inspection.
- Cell indices are 1-based: `row=1, column=1` is `A1`.
- For very large files, use `read_only=True` for reading or `write_only=True` for writing.
- Formulas are preserved but not evaluated by openpyxl. Recalculation happens via `scripts/recalc.py` (LibreOffice).

## When editing a file with established conventions

Inspect first: open the workbook, walk the existing sheets, and record column headers, number formats, fill colors, font colors, and formula patterns. Match them exactly. The defaults in `financial-model-standards.md` apply only when the file has no established style.
