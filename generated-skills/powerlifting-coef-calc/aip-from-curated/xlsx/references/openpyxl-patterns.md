# openpyxl & pandas Code Patterns

Load when authoring Python that reads, edits, or writes `.xlsx`/`.xlsm` files.

## Reading & analyzing with pandas

```python
import pandas as pd

df = pd.read_excel('file.xlsx')                          # first sheet
all_sheets = pd.read_excel('file.xlsx', sheet_name=None) # dict of sheets

df.head()
df.info()
df.describe()

df.to_excel('output.xlsx', index=False)
```

Tips:
- Specify dtype to avoid inference issues: `pd.read_excel('file.xlsx', dtype={'id': str})`
- Read specific columns for large files: `pd.read_excel('file.xlsx', usecols=['A', 'C', 'E'])`
- Parse dates: `pd.read_excel('file.xlsx', parse_dates=['date_column'])`

## Creating new files with openpyxl

```python
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

wb = Workbook()
sheet = wb.active

sheet['A1'] = 'Hello'
sheet['B1'] = 'World'
sheet.append(['Row', 'of', 'data'])

sheet['B2'] = '=SUM(A1:A10)'   # formula, not a Python-computed value

sheet['A1'].font = Font(bold=True, color='FF0000')
sheet['A1'].fill = PatternFill('solid', start_color='FFFF00')
sheet['A1'].alignment = Alignment(horizontal='center')

sheet.column_dimensions['A'].width = 20

wb.save('output.xlsx')
```

## Editing existing files while preserving formulas & formatting

```python
from openpyxl import load_workbook

wb = load_workbook('existing.xlsx')
sheet = wb.active                # or wb['SheetName']

for sheet_name in wb.sheetnames:
    sheet = wb[sheet_name]
    print(f"Sheet: {sheet_name}")

sheet['A1'] = 'New Value'
sheet.insert_rows(2)
sheet.delete_cols(3)

new_sheet = wb.create_sheet('NewSheet')
new_sheet['A1'] = 'Data'

wb.save('modified.xlsx')
```

## Library selection

- **pandas** — data analysis, bulk operations, simple data export.
- **openpyxl** — complex formatting, formulas, Excel-specific features.

## openpyxl gotchas

- Cell indices are 1-based: `row=1, column=1` is `A1`.
- `load_workbook('file.xlsx', data_only=True)` reads calculated values, but if you save after opening with `data_only=True`, formulas are replaced with values and permanently lost.
- For large files: `read_only=True` for reading, `write_only=True` for writing.
- Formulas are stored as strings; they are NOT evaluated by openpyxl — run `scripts/recalc.py` to compute values.

## Code style for Python that drives Excel

- Write minimal, concise Python without unnecessary comments.
- Avoid verbose variable names and redundant operations.
- Avoid unnecessary `print` statements.

## Code style for the Excel files themselves

- Add comments on cells with complex formulas or important assumptions.
- Document data sources for hardcoded values.
- Include notes for key calculations and model sections.
