# Reading and modelling Excel case data (pandas / openpyxl)

Load on the general-model branch, or whenever you write your own code against the workbook.
The container has python3 with pandas 2.2.3, openpyxl 3.1.5, pypdf 5.1.0 only: no LibreOffice
(so no `recalc.py` formula recalculation), no pdfplumber, no poppler/qpdf CLIs.

## Loading

```python
import pandas as pd
raw = pd.read_excel(path, sheet_name=None, header=None)   # every sheet, no header guessing
t = pd.read_excel(path, sheet_name="Data", header=8)       # header at Excel row 9 -> header=8
```
- Excel rows are 1-indexed; DataFrame row i (header=None) is Excel row i+1. Column 64 = BL, not BK.
- Case workbooks (ModelOff style) start with title rows, a `Formats` legend sheet (style guide only, no data) and a table whose header is several rows down and columns start at C. Use the header row from `workbook_summary`.
- `openpyxl.load_workbook(path, data_only=True)` reads cached formula values; without it formulas come back as strings. Never save a workbook opened with `data_only=True` (formulas are lost). `read_only=True` for big files.
- Specify dtypes when ids look numeric: `dtype={'id': str}`; parse dates with `parse_dates=[...]`; for a few columns use `usecols`.

## Pitfalls to check before computing

- Blank rows inside the table, and values sitting outside the header columns (a row pasted to the right). `workbook_summary` NOTE lines flag them. Rebuild by the record's own id, never by row position.
- NaN: check with `pd.notna()`; `dropna()` can silently drop a whole record.
- Far-right columns: annual data often sits in columns 50+.
- Multiple matches: search all occurrences of a label, not just the first.
- Numbers stored as text: coerce with `pd.to_numeric(errors="coerce")` and count what failed.
- Off-by-one in ranges and pairings (game 1 vs 2 means odd/even ids, not row parity after a gap).
- Division by zero; unintended circularity when a definition refers to itself.

## Modelling method (adapted from the spreadsheet build checklist)

1. Put every assumption from the background (rates, fixed scores, thresholds) in named variables, not inline literals.
2. Compute per-record results in vectorised pandas, one column per rule, then aggregate.
3. Test 2-3 records by hand against the rule text before trusting the full column.
4. Test edge cases the rules imply (zero, ties, equal values, missing).
5. Sanity-check totals and counts (record count = expected, no NaN in result columns).
6. Answer only what was asked; units and sign as the question states them.
