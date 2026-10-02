# pypdf patterns for background PDFs

Load on demand when the extracted background text in state is not enough. The task's container has `pypdf==5.1.0` preinstalled and no other PDF libraries; do not import `pdfplumber`, `pypdfium2`, `reportlab`, or `pdf-lib` — they are not available.

## Basic text extraction

```python
from pypdf import PdfReader

reader = PdfReader("/root/background.pdf")
for i, page in enumerate(reader.pages, start=1):
    print(f"--- Page {i} ---")
    print(page.extract_text() or "")
```

## Metadata

```python
meta = PdfReader("/root/background.pdf").metadata
print(meta.title, meta.author, meta.subject)
```

## Extract a specific page's text

```python
reader = PdfReader("/root/background.pdf")
page = reader.pages[2]  # 0-indexed
text = page.extract_text() or ""
```

## When pypdf's text is garbled

Text extraction from PDFs is inherently approximate:

- Whitespace between adjacent glyphs may collapse or explode; numbers still parse.
- Tables and columns may reflow into a single stream; the header row often appears right before the data row.
- Ligatures (fi, fl) and math symbols may drop or become spaces; a formula like `A + B` can appear as `A B`.

Workarounds inside this skill's constraints:

- Read the raw text and mentally reconstruct table structure from the surrounding prose.
- Extract page by page and inspect the pages you need; do not treat the concatenated blob as a single flow.
- If a rule or formula from the PDF looks wrong, cross-check it against the raw data: the data is authoritative; the extracted rule text may be missing a symbol.
- Do **not** install other PDF libraries — the container is frozen; import failures cost latency and do not help.

## What this skill does not cover

Form filling, PDF creation, page merging, watermarking, encryption, image extraction, and OCR are all documented in the upstream `pdf` skill (see `source/pdf/`) but are out of scope for the finance-QA task, which only needs to read a background document. If a future task needs any of them, extend this skill rather than adding one-off scripts.
