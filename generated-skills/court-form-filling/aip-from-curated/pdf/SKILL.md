---
name: pdf
description: Comprehensive PDF manipulation toolkit for extracting text and tables, creating new PDFs, merging/splitting documents, and handling forms. When Claude needs to fill in a PDF form or programmatically process, generate, or analyze PDF documents at scale.
license: Proprietary. LICENSE.txt has complete terms
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Process, generate, and analyze PDF documents — text and table extraction,
  creation, merge/split/rotate, OCR, watermarking, encryption, and form
  filling. Canonical code samples for each library live in this body; deeper
  examples and JavaScript options live in reference.md; the form-filling
  pipeline lives in forms.md and the bundled scripts/.

trigger_when:
  - User asks to extract text or tables from a PDF.
  - User asks to fill a PDF form.
  - User asks to merge, split, rotate, watermark, or encrypt PDFs.
  - User asks to create a PDF programmatically.
  - User mentions OCR of scanned PDFs.
  - Any task that requires programmatic analysis or generation of PDF documents at scale.

do_not_use_when:
  - The task is editing Word or other non-PDF office documents.
  - No PDF input or output is involved.

steps:
  - name: classify-task
    description: >
      Identify which family the request belongs to — extract (text/tables/images),
      create, transform (merge/split/rotate/watermark/encrypt), or fill form —
      so the right tool is chosen on the first try.
  - name: choose-tool
    description: >
      Map task to library using the quick reference below. pypdf for
      merge/split/rotate/metadata/encrypt; pdfplumber for layout-aware text
      and tables; reportlab for creation; pypdfium2 for fast rendering;
      pytesseract + pdf2image for OCR; qpdf / pdftotext / pdfimages / pdftk
      for command-line work; pdf-lib / pdfjs-dist for JavaScript.
  - name: execute
    description: >
      Apply the chosen tool using the canonical recipes below. For advanced
      features (pypdfium2, JavaScript libraries, table tuning, batch
      processing, cropping, optimization), read reference.md.
  - name: handle-forms
    description: >
      For form filling, follow forms.md exactly. First run
      `python scripts/check_fillable_fields.py <file.pdf>` to detect whether
      the PDF carries fillable AcroForm fields, then take the matching branch.
    one_of:
      - >-
        Fillable AcroForm: run `scripts/extract_form_field_info.py
        <input.pdf> <field_info.json>`, render pages with
        `scripts/convert_pdf_to_images.py` to identify each field, write
        `field_values.json`, then run `scripts/fill_fillable_fields.py
        <input pdf> <field_values.json> <output pdf>`.
      - >-
        No fillable fields: convert pages to PNG with
        `scripts/convert_pdf_to_images.py`, hand-build `fields.json` with
        non-overlapping label and entry bounding boxes, validate with
        `scripts/check_bounding_boxes.py` and visually inspect
        `scripts/create_validation_image.py` output, then run
        `scripts/fill_pdf_form_with_annotations.py <input_pdf>
        <fields.json> <output_pdf>`.
  - name: verify
    description: >
      Render or open the result to confirm pages, text, or form values are
      correct. For non-fillable forms, the bounding-box validation images
      must be visually inspected before annotations are written.

decisions:
  - signal: PDF carries fillable AcroForm fields (check_fillable_fields.py reports fillable).
    action: Take the fillable branch — extract_form_field_info.py → field_values.json → fill_fillable_fields.py.
  - signal: PDF has no fillable form fields.
    action: Take the visual-annotation branch — convert_pdf_to_images.py → fields.json → check_bounding_boxes.py → create_validation_image.py → fill_pdf_form_with_annotations.py.
  - signal: PDF is a scanned image with no extractable text layer.
    action: OCR with pdf2image + pytesseract before further extraction.
  - signal: PDF is encrypted or password-protected.
    action: Decrypt first — `qpdf --password=… --decrypt` or `pypdf` `reader.decrypt(password)`.
  - signal: Tables need to land in a spreadsheet.
    action: pdfplumber `page.extract_tables()` → pandas DataFrame → `to_excel()`.
  - signal: Need fast batch image rendering of every page.
    action: pypdfium2 `page.render(scale=…).to_pil()` — see reference.md.
  - signal: Very large PDF; pypdf.extract_text() is slow or memory-heavy.
    action: Switch to `pdftotext -layout` or stream page-by-page with pypdfium2 / pdfplumber.
  - signal: PDF appears corrupted.
    action: >-
      Run `qpdf --check input.pdf`, then `qpdf --replace-input` or
      `qpdf --fix-qdf` to repair (see reference.md).

modes:
  - name: python-first
    body: >
      Default. Use pypdf / pdfplumber / reportlab / pypdfium2 in-process.
      Best when the agent already has a Python runtime and the task is
      embedded in a larger Python workflow.
  - name: cli-first
    body: >
      Reach for qpdf, pdftotext, pdfimages, pdftoppm, pdftk when shelling
      out is simpler than writing Python — e.g., one-shot merges, split by
      page count, password removal, repair, or bulk image extraction.
      Faster startup, no Python deps.
  - name: javascript
    body: >
      Use pdf-lib (Node/browser) or pdfjs-dist (browser) when the surrounding
      app is JavaScript. pdf-lib preserves form structure better than most
      alternatives; pdfjs-dist gives text-with-coordinates and annotation
      enumeration. See reference.md for examples.

search_shortcuts:
  - category: Python libraries
    body: |
      pypdf — merge, split, rotate, metadata, encrypt. BSD.
      pdfplumber — layout-aware text and table extraction. MIT.
      pypdfium2 — fast PDFium-backed rendering / image generation; PyMuPDF alternative. Apache/BSD.
      reportlab — PDF creation, Platypus flow documents, styled tables. BSD.
      pytesseract + pdf2image — OCR for scanned PDFs.
  - category: Command-line tools
    body: |
      pdftotext (poppler-utils) — text extraction; `-layout` preserves columns; `-f`/`-l` for page range.
      pdftoppm / pdfimages (poppler-utils) — page-to-image rendering and embedded-image extraction.
      qpdf — merge/split/rotate/encrypt/linearize/optimize; `--check` and `--fix-qdf` repair.
      pdftk (if available) — simple merge/split/rotate; `burst` for one-page-per-file.
  - category: JavaScript libraries
    body: |
      pdf-lib (MIT) — load, create, modify; preserves form structure.
      pdfjs-dist (Apache) — Mozilla's renderer; text with coordinates; annotation/form enumeration.

scenarios:
  - need: Merge several PDFs into one.
    action: pypdf — loop `PdfReader` pages into a single `PdfWriter`; or `qpdf --empty --pages a.pdf b.pdf -- merged.pdf`.
  - need: Split a PDF into one file per page.
    action: pypdf — for each page index, instantiate a fresh `PdfWriter` and write `page_{i+1}.pdf`. Or `qpdf --split-pages=1`.
  - need: Extract layout-preserving text.
    action: >-
      `pdftotext -layout input.pdf out.txt`, or pdfplumber
      `page.extract_text()` for per-page control.
  - need: Extract tables to a spreadsheet.
    action: pdfplumber `page.extract_tables()` per page → pandas DataFrame per table → `pd.concat(...).to_excel("extracted_tables.xlsx")`.
  - need: Create a styled multi-page report.
    action: reportlab Platypus — `SimpleDocTemplate` + `Paragraph`/`Spacer`/`PageBreak` from `getSampleStyleSheet()`; advanced styling with `Table` + `TableStyle` (see reference.md).
  - need: Extract text from a scanned PDF (no text layer).
    action: >-
      `pdf2image.convert_from_path(...)` → loop pages →
      `pytesseract.image_to_string(image)`.
  - need: Add a watermark to every page.
    action: pypdf — load watermark page; loop `reader.pages`; `page.merge_page(watermark)`; `writer.add_page(page)`.
  - need: Password-protect a PDF.
    action: pypdf — `writer.encrypt("userpassword", "ownerpassword")` before writing.
  - need: Fill a court form that has fillable AcroForm fields.
    action: scripts/check_fillable_fields.py → scripts/extract_form_field_info.py → render pages via scripts/convert_pdf_to_images.py to identify each field → write field_values.json → scripts/fill_fillable_fields.py.
  - need: Fill a court form that has no fillable fields.
    action: scripts/convert_pdf_to_images.py → analyze PNGs and hand-build fields.json with label and entry bounding boxes → scripts/check_bounding_boxes.py + scripts/create_validation_image.py → visually inspect → scripts/fill_pdf_form_with_annotations.py.

anti_patterns:
  - Writing form-filling code before running scripts/check_fillable_fields.py — the right pipeline depends on whether AcroForm fields exist.
  - Letting label and entry bounding boxes overlap in fields.json. Entry boxes must cover only the area where text is entered; label boxes must contain only the label text.
  - For checkboxes, sizing the entry bounding box to include the label text instead of centering it on the square. Red rectangle must land on the square; blue rectangle covers the label.
  - Skipping visual inspection of the validation images before running fill_pdf_form_with_annotations.py.
  - Using pypdf.extract_text() on very large documents — prefer `pdftotext -layout` or pdfplumber streamed per page.
  - Treating a scanned PDF as if it had a text layer; fall back to OCR (pdf2image + pytesseract) when extraction returns empty strings.
  - Ignoring `reader.is_encrypted` and crashing on protected PDFs; decrypt with qpdf or `reader.decrypt(password)` first.

# ---------------------------------------------------------------------------
# Canonical recipes
# Inlined so the agent can act without loading reference.md for common cases.
# Push to reference.md only for advanced or JavaScript variants.
# ---------------------------------------------------------------------------

scope_and_approval: |
  Pure read/write file operations on user-supplied PDFs. No network calls
  are required. Encryption, decryption, and form filling all happen
  locally. Confirm with the user before overwriting an input PDF in place
  — every recipe below writes to a distinct output path by default.

  Quick-start read:
      from pypdf import PdfReader, PdfWriter
      reader = PdfReader("document.pdf")
      print(f"Pages: {len(reader.pages)}")
      text = "".join(page.extract_text() for page in reader.pages)

  pypdf — merge:
      writer = PdfWriter()
      for pdf_file in ["doc1.pdf", "doc2.pdf", "doc3.pdf"]:
          for page in PdfReader(pdf_file).pages:
              writer.add_page(page)
      with open("merged.pdf", "wb") as output:
          writer.write(output)

  pypdf — split one-page-per-file:
      reader = PdfReader("input.pdf")
      for i, page in enumerate(reader.pages):
          writer = PdfWriter()
          writer.add_page(page)
          with open(f"page_{i+1}.pdf", "wb") as output:
              writer.write(output)

  pypdf — metadata:
      meta = PdfReader("document.pdf").metadata
      # meta.title, meta.author, meta.subject, meta.creator

  pypdf — rotate page 1 by 90°:
      reader = PdfReader("input.pdf"); writer = PdfWriter()
      page = reader.pages[0]; page.rotate(90); writer.add_page(page)
      with open("rotated.pdf", "wb") as output: writer.write(output)

  pypdf — watermark every page:
      watermark = PdfReader("watermark.pdf").pages[0]
      reader = PdfReader("document.pdf"); writer = PdfWriter()
      for page in reader.pages:
          page.merge_page(watermark); writer.add_page(page)
      with open("watermarked.pdf", "wb") as output: writer.write(output)

  pypdf — password-protect:
      writer.encrypt("userpassword", "ownerpassword")  # before write()

  pdfplumber — text and tables:
      with pdfplumber.open("document.pdf") as pdf:
          for i, page in enumerate(pdf.pages):
              print(page.extract_text())
              for j, table in enumerate(page.extract_tables()):
                  for row in table: print(row)

  pdfplumber → pandas → Excel:
      import pandas as pd
      all_tables = []
      with pdfplumber.open("document.pdf") as pdf:
          for page in pdf.pages:
              for table in page.extract_tables():
                  if table:
                      all_tables.append(pd.DataFrame(table[1:], columns=table[0]))
      if all_tables:
          pd.concat(all_tables, ignore_index=True).to_excel("extracted_tables.xlsx", index=False)

  reportlab — basic canvas:
      from reportlab.lib.pagesizes import letter
      from reportlab.pdfgen import canvas
      c = canvas.Canvas("hello.pdf", pagesize=letter)
      _, height = letter
      c.drawString(100, height - 100, "Hello World!")
      c.line(100, height - 140, 400, height - 140)
      c.save()

  reportlab — Platypus multi-page (see reference.md for styled tables):
      from reportlab.lib.pagesizes import letter
      from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
      from reportlab.lib.styles import getSampleStyleSheet
      doc = SimpleDocTemplate("report.pdf", pagesize=letter)
      styles = getSampleStyleSheet()
      story = [Paragraph("Report Title", styles['Title']), Spacer(1, 12),
               Paragraph("Body " * 20, styles['Normal']), PageBreak(),
               Paragraph("Page 2", styles['Heading1']),
               Paragraph("Content for page 2", styles['Normal'])]
      doc.build(story)

  OCR scanned PDF:
      from pdf2image import convert_from_path
      import pytesseract
      text = ""
      for i, image in enumerate(convert_from_path("scanned.pdf")):
          text += f"Page {i+1}:\n{pytesseract.image_to_string(image)}\n\n"

  CLI — pdftotext:
      pdftotext input.pdf output.txt           # plain
      pdftotext -layout input.pdf output.txt   # preserve columns
      pdftotext -f 1 -l 5 input.pdf output.txt # pages 1-5

  CLI — qpdf:
      qpdf --empty --pages a.pdf b.pdf -- merged.pdf
      qpdf input.pdf --pages . 1-5 -- pages1-5.pdf
      qpdf input.pdf output.pdf --rotate=+90:1
      qpdf --password=secret --decrypt encrypted.pdf decrypted.pdf

  CLI — pdftk (if installed):
      pdftk a.pdf b.pdf cat output merged.pdf
      pdftk input.pdf burst
      pdftk input.pdf rotate 1east output rotated.pdf

  CLI — pdfimages:
      pdfimages -j input.pdf output_prefix     # writes output_prefix-000.jpg, ...

  Quick reference table:
      Merge PDFs            pypdf          writer.add_page(page)
      Split PDFs            pypdf          one page per file
      Extract text          pdfplumber     page.extract_text()
      Extract tables        pdfplumber     page.extract_tables()
      Create PDFs           reportlab      Canvas or Platypus
      CLI merge             qpdf           qpdf --empty --pages ...
      OCR scanned PDFs      pytesseract    convert to image first
      Fill PDF forms        pdf-lib / pypdf — see forms.md

  Next steps and where to look:
      - Advanced pypdfium2 usage → reference.md
      - JavaScript libraries (pdf-lib, pdfjs-dist) → reference.md
      - Form filling, fillable and non-fillable pipelines → forms.md
      - Troubleshooting (corrupted, encrypted, scanned) → reference.md
```
