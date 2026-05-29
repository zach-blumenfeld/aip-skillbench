# pandas patterns

Use pandas when the task is data analysis, bulk reads/writes, statistics, group-bys, pivots, or simple tabular exports. Pandas drops formulas and formatting, so reach for openpyxl when those matter.

## Read / inspect / write

```python
import pandas as pd

# Read
df = pd.read_excel('file.xlsx')                                 # first sheet
all_sheets = pd.read_excel('file.xlsx', sheet_name=None)         # dict of sheets

# Analyze
df.head()
df.info()
df.describe()

# Write
df.to_excel('output.xlsx', index=False)
```

## Options worth knowing

- **Force dtypes** to avoid inference surprises: `pd.read_excel('file.xlsx', dtype={'id': str})`.
- **Pick columns only** for big files: `pd.read_excel('file.xlsx', usecols=['A', 'C', 'E'])`.
- **Parse dates** explicitly: `pd.read_excel('file.xlsx', parse_dates=['date_column'])`.

## NaN-aware references

When using pandas results to drive openpyxl writes, guard with `pd.notna()` before turning a value into a cell write — otherwise you get `'nan'` strings in the workbook.
