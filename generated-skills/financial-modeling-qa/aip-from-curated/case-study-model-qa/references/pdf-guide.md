# PDF text extraction (adapted from the curated `pdf` skill)

Load this when `pdf_text` is empty or garbled, has a scanned-PDF warning, or loses a table you need.

- The task container has **pypdf only**: `PdfReader(path).pages[i].extract_text()`. pdfplumber, reportlab, pypdfium2, and pdf2image are not installed. Don't import them unless you install them first.
- pypdf warnings like "Ignoring wrong pointing object" are harmless.
- Tables come out as lines of space-separated cells. Rebuild the scoring or assumption table by reading the lines in order. A criterion that wraps over several lines ("multiplied by") belongs to the row above it.
- Encrypted: `if reader.is_encrypted: reader.decrypt("")` or the password.
- If installed, `pdftotext -layout in.pdf out.txt` keeps column layout. `pdftotext -f 1 -l 5` extracts pages 1-5. `pdftotext -bbox-layout` gives coordinates.
- If pdfplumber is installed, `page.extract_tables()` works for ruled tables. `page.within_bbox((x0, top, x1, bottom)).extract_text()` extracts a region.
- Scanned PDFs (almost no text): OCR with pytesseract + pdf2image (`convert_from_path` then `image_to_string`), if they can be installed. Otherwise read a rendered page image.
- Corrupted files: `qpdf --check in.pdf`.
- Metadata: `reader.metadata.title` and `.author`.
