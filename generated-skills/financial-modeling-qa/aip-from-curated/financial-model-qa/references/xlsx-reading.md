# Reading the workbook beyond what `extract_sources.py` returns

`extract_sources.py` emits every non-empty cell on every sheet with value, formula, number
format, and comment. Load this only if the first pass isn't enough.

## Re-open with pandas when you need tabular analysis
```python
import pandas as pd
sheets = pd.read_excel(xlsx_path, sheet_name=None)      # dict of DataFrames
df = sheets["<name>"]
```
`read_excel` returns cached calculated values; it does *not* see formulas. If the workbook was never opened in Excel/LibreOffice its cached values can be `None`.

## Re-open with openpyxl for formulas or formatting
```python
import openpyxl
wb_val = openpyxl.load_workbook(xlsx_path, data_only=True)   # cached calc values
wb_frm = openpyxl.load_workbook(xlsx_path, data_only=False)  # formulas as strings
cell = wb_val["Model"]["B5"]      # cell.value is the number
formula = wb_frm["Model"]["B5"].value  # "=SUM(...)" if a formula
```
Opening with `data_only=True` and saving overwrites formulas with values permanently — never save a `data_only` workbook.

## Cross-sheet references
Formulas like `=Assumptions!$B$5` resolve against the sheet named before `!`. Named ranges (workbook_defined_names in `xlsx_data`) resolve to `SheetName!$A$1:$B$3`-style refs.

## Column letter / index math
Excel columns are letters, DataFrame columns are 0-indexed. `openpyxl.utils.get_column_letter(64)` returns `"BL"`; FY columns in large models often sit at col 50+.

## Zero / null handling
Pandas sees empty cells as `NaN`; check with `pd.notna()` before arithmetic. In openpyxl, empty cells read as `None`; empty strings are distinct from `None`.
