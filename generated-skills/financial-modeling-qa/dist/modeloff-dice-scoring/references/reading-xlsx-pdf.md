# Reading the workbook and PDF with custom code

Load only when the scripts do not cover the question and you write your own pandas / openpyxl / pypdf code. Adapted from the curated `xlsx` and `pdf` skills (see `source/`).

## What the container has

pandas 2.2.3, openpyxl 3.1.5, pypdf 5.1.0, Python 3 (Ubuntu 24.04). Not available: LibreOffice (so no formula recalculation), pdfplumber, reportlab, poppler (`pdftotext`, `pdfimages`), qpdf, pytesseract/pdf2image (no OCR), pypdfium2. Install extras with `pip install --break-system-packages <pkg>` only if the network allows; prefer the stack above.

## pandas

```python
import pandas as pd
all_sheets = pd.read_excel('/root/data.xlsx', sheet_name=None, header=None)  # dict of DataFrames, raw grid
df = pd.read_excel('/root/data.xlsx', sheet_name='Data', header=None)
df.head(); df.info(); df.describe()
```

- Use `header=None` first: ModelOff sheets have title rows, so the real header is several rows down and data starts in column C. Locate the header row by its text, then slice.
- Positions: DataFrame row i (with `header=None`) = Excel row i+1; column index 0 = A. Confirm column letters (column 64 = BL, not BK) before quoting a cell.
- Large files: `usecols=[...]` to read only some columns; `dtype={'id': str}` to stop type inference; `parse_dates=[...]` for dates.
- `dropna(how='all')` silently removes blank rows; first list them — a blank row inside a table is a defect to investigate, not noise. Search every occurrence of a value, not just the first; scan far-right columns for stray values.
- Check NaN with `pd.notna()` before arithmetic.

## openpyxl

```python
from openpyxl import load_workbook
wb = load_workbook('/root/data.xlsx', data_only=True)   # cached values, not formula strings
for ws in wb: print(ws.title, ws.dimensions, ws.sheet_state)
ws = wb['Data']; ws.cell(row=10, column=3).value        # 1-based rows and columns
```

- `data_only=True` gives values; a formula cell never calculated in Excel reads `None`. Saving a workbook opened with `data_only=True` replaces formulas with values permanently — never save over the input.
- `read_only=True` for very large files (faster, but no random `ws.cell` writes).
- Hidden sheets (`sheet_state != 'visible'`) and cells outside `ws.dimensions` are worth a look when numbers do not reconcile.

## If you write a model workbook (not required for answer.txt)

Use formulas, not hardcoded Python results (`=SUM(B2:B9)`, not the number); keep assumptions in their own cells; aim for zero formula errors (#REF!, #DIV/0!, #VALUE!, #N/A, #NAME?). Without LibreOffice the formulas stay uncalculated in the file, so compute the answer in Python and use the workbook only as documentation. Test 2–3 formulas before filling a range; check off-by-one ranges and cross-sheet references (`Sheet1!A1`).

## pypdf

```python
from pypdf import PdfReader
r = PdfReader('/root/background.pdf')
if r.is_encrypted: r.decrypt('')
text = "\n".join(p.extract_text() or "" for p in r.pages)
```

- Tables in the PDF flatten to running text: "Category Criteria Score" rows come out as one line per category with the fixed score at the end (`... (e.g. 3-6-3-6-6-6) 30`). Read the numbers next to each category name carefully.
- `r.metadata` gives title/author if you need to identify the case.
- Empty text on a page means a scanned image; no OCR is available here.
