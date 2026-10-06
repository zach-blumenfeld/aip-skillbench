# Reading the PDF beyond what `extract_sources.py` returns

`extract_sources.py` emits full plaintext per page (via `pypdf`), which is enough for
narrative questions. Load this if you need tables, metadata, or layout that pypdf drops.

## Tables and layout
`pypdf.extract_text()` concatenates text in reading order without column structure. If the
background has tables you must read as rows and columns, prefer `pdfplumber`:
```python
import pdfplumber
with pdfplumber.open(pdf_path) as pdf:
    for page in pdf.pages:
        for table in page.extract_tables():
            # table is list[list[str]]; first row is often the header
            ...
```
`pdfplumber` is not guaranteed to be installed in the task container; fall back to parsing the pypdf text yourself if it isn't.

## Metadata
```python
from pypdf import PdfReader
meta = PdfReader(pdf_path).metadata   # .title, .author, .subject, .creator
```

## Scanned / image-only pages
If `extract_text()` returns an empty string on every page, the PDF is scanned. OCR via
`pytesseract` + `pdf2image` is possible but neither library is in the task container; fall
back to using the xlsx and reporting the gap explicitly in the answer.

## When `extract_text` output is garbled
Column-break reordering, ligature collapse, and header/footer noise are known pypdf
quirks. Try `pdfplumber` first, then narrow to a single page with
`PdfReader(pdf_path).pages[i].extract_text()` for debugging.
