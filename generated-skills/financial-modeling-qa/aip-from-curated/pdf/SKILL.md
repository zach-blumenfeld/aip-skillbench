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
  Process, generate, and analyze PDF documents programmatically. Covers text
  and table extraction, PDF creation, merging/splitting, rotation, metadata,
  OCR of scanned PDFs, watermarking, image extraction, password protection,
  and form filling. Bias toward the right tool per task: pypdf for structural
  operations, pdfplumber for text/table extraction, reportlab for authoring,
  qpdf/pdftotext for command-line workflows, and the bundled scripts for
  form filling.

trigger_when:
  - User mentions PDFs, PDF forms, or document extraction.
  - Task requires extracting text or tables from a PDF.
  - Task requires generating a new PDF programmatically.
  - Task requires merging, splitting, rotating, or watermarking PDFs.
  - Task requires filling a fillable PDF form (see references/forms.md).
  - Task requires OCR over scanned PDFs.
  - Working with PDF metadata or password-protected PDFs.

steps:
  - name: classify-task
    description: >
      Identify which family the task belongs to — extraction (text/tables),
      authoring (create new PDF), structural (merge/split/rotate/watermark),
      forms (fill fillable PDF), OCR (scanned PDF), or security (passwords).
      The classification picks both the library and the section to consult.
  - name: pick-tool
    description: >
      Choose the tool per the Quick Reference decisions table below. Default
      to the Python libraries listed in search_shortcuts; fall back to the
      command-line tools when a shell-only workflow fits better. For advanced
      pypdfium2, JavaScript (pdf-lib), or troubleshooting, read
      references/reference.md.
    depends_on: [classify-task]
  - name: handle-forms
    description: >
      If filling a PDF form, read references/forms.md and follow its
      instructions end-to-end. The scripts/ directory contains the helpers
      it references (extract_form_field_info.py, fill_fillable_fields.py,
      fill_pdf_form_with_annotations.py, check_bounding_boxes.py,
      check_fillable_fields.py, convert_pdf_to_images.py,
      create_validation_image.py).
    depends_on: [classify-task]
  - name: execute
    description: >
      Run the chosen library calls or CLI commands. Use the code snippets in
      search_shortcuts as starting points. For multi-page or batch work,
      stream pages rather than loading whole documents into memory.
    depends_on: [pick-tool]
  - name: verify
    description: >
      Spot-check output — for extraction, sample a page's text/tables; for
      authoring or structural changes, reopen the resulting PDF and verify
      page count, rotation, and that pages render. For forms, generate a
      validation image with create_validation_image.py.
    depends_on: [execute]

decisions:
  - signal: Need to merge PDFs.
    action: Use pypdf (`PdfWriter().add_page(page)` over each reader's pages); CLI alternative is `qpdf --empty --pages ...`.
  - signal: Need to split PDFs.
    action: Use pypdf — one `PdfWriter` per output file. CLI alternative is `qpdf input.pdf --pages . 1-5 -- out.pdf`.
  - signal: Need to extract plain text.
    action: Use pdfplumber `page.extract_text()`. CLI alternative is `pdftotext` (add `-layout` to preserve layout).
  - signal: Need to extract tables.
    action: Use pdfplumber `page.extract_tables()`; convert to `pandas.DataFrame` for downstream analysis.
  - signal: Need to create a new PDF.
    action: Use reportlab — `canvas.Canvas` for low-level drawing, `SimpleDocTemplate` + Platypus for flowable multi-page documents.
  - signal: Need to merge/split from the shell.
    action: Use qpdf (`--empty --pages` for merge, `--pages . N-M --` for split).
  - signal: PDF is scanned (no embedded text).
    action: OCR with pytesseract — convert pages to images via `pdf2image.convert_from_path` first.
  - signal: Need to fill a fillable PDF form.
    action: Read references/forms.md; use the helpers in scripts/ — start with extract_form_field_info.py, then fill_fillable_fields.py or fill_pdf_form_with_annotations.py.
  - signal: Need advanced pypdfium2, JavaScript pdf-lib, or troubleshooting guidance.
    action: Read references/reference.md.

search_shortcuts:
  - category: Python — pypdf (structural operations)
    body: |
      Basic read and text extraction:
      ```python
      from pypdf import PdfReader, PdfWriter

      reader = PdfReader("document.pdf")
      print(f"Pages: {len(reader.pages)}")
      text = "".join(page.extract_text() for page in reader.pages)
      ```

      Merge:
      ```python
      writer = PdfWriter()
      for pdf_file in ["doc1.pdf", "doc2.pdf", "doc3.pdf"]:
          for page in PdfReader(pdf_file).pages:
              writer.add_page(page)
      with open("merged.pdf", "wb") as output:
          writer.write(output)
      ```

      Split (one page per file):
      ```python
      reader = PdfReader("input.pdf")
      for i, page in enumerate(reader.pages):
          writer = PdfWriter()
          writer.add_page(page)
          with open(f"page_{i+1}.pdf", "wb") as output:
              writer.write(output)
      ```

      Metadata:
      ```python
      meta = PdfReader("document.pdf").metadata
      print(meta.title, meta.author, meta.subject, meta.creator)
      ```

      Rotate (90 deg clockwise on page 0):
      ```python
      reader = PdfReader("input.pdf")
      writer = PdfWriter()
      page = reader.pages[0]
      page.rotate(90)
      writer.add_page(page)
      with open("rotated.pdf", "wb") as output:
          writer.write(output)
      ```

  - category: Python — pdfplumber (text and table extraction)
    body: |
      Extract text with layout:
      ```python
      import pdfplumber
      with pdfplumber.open("document.pdf") as pdf:
          for page in pdf.pages:
              print(page.extract_text())
      ```

      Extract tables:
      ```python
      with pdfplumber.open("document.pdf") as pdf:
          for i, page in enumerate(pdf.pages):
              for j, table in enumerate(page.extract_tables()):
                  print(f"Table {j+1} on page {i+1}:")
                  for row in table:
                      print(row)
      ```

      Tables to a combined Excel workbook:
      ```python
      import pandas as pd, pdfplumber
      with pdfplumber.open("document.pdf") as pdf:
          all_tables = []
          for page in pdf.pages:
              for table in page.extract_tables():
                  if table:
                      df = pd.DataFrame(table[1:], columns=table[0])
                      all_tables.append(df)
      if all_tables:
          pd.concat(all_tables, ignore_index=True).to_excel("extracted_tables.xlsx", index=False)
      ```

  - category: Python — reportlab (create PDFs)
    body: |
      Low-level canvas:
      ```python
      from reportlab.lib.pagesizes import letter
      from reportlab.pdfgen import canvas

      c = canvas.Canvas("hello.pdf", pagesize=letter)
      width, height = letter
      c.drawString(100, height - 100, "Hello World!")
      c.drawString(100, height - 120, "This is a PDF created with reportlab")
      c.line(100, height - 140, 400, height - 140)
      c.save()
      ```

      Multi-page Platypus document:
      ```python
      from reportlab.lib.pagesizes import letter
      from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
      from reportlab.lib.styles import getSampleStyleSheet

      doc = SimpleDocTemplate("report.pdf", pagesize=letter)
      styles = getSampleStyleSheet()
      story = [
          Paragraph("Report Title", styles['Title']),
          Spacer(1, 12),
          Paragraph("This is the body of the report. " * 20, styles['Normal']),
          PageBreak(),
          Paragraph("Page 2", styles['Heading1']),
          Paragraph("Content for page 2", styles['Normal']),
      ]
      doc.build(story)
      ```

  - category: Command-line — pdftotext (poppler-utils)
    body: |
      ```bash
      pdftotext input.pdf output.txt              # extract text
      pdftotext -layout input.pdf output.txt      # preserve layout
      pdftotext -f 1 -l 5 input.pdf output.txt    # pages 1-5 only
      ```

  - category: Command-line — qpdf
    body: |
      ```bash
      qpdf --empty --pages file1.pdf file2.pdf -- merged.pdf   # merge
      qpdf input.pdf --pages . 1-5 -- pages1-5.pdf             # split pages 1-5
      qpdf input.pdf --pages . 6-10 -- pages6-10.pdf           # split pages 6-10
      qpdf input.pdf output.pdf --rotate=+90:1                 # rotate page 1 by 90 deg
      qpdf --password=mypassword --decrypt encrypted.pdf decrypted.pdf
      ```

  - category: Command-line — pdftk (if available)
    body: |
      ```bash
      pdftk file1.pdf file2.pdf cat output merged.pdf   # merge
      pdftk input.pdf burst                              # split into pg_0001.pdf, ...
      pdftk input.pdf rotate 1east output rotated.pdf    # rotate page 1 east (90 CW)
      ```

  - category: Command-line — pdfimages (poppler-utils)
    body: |
      ```bash
      pdfimages -j input.pdf output_prefix
      # writes output_prefix-000.jpg, output_prefix-001.jpg, ...
      ```

  - category: Quick reference (task → tool)
    body: |
      | Task                | Best Tool                          | Command/Code                      |
      |---------------------|------------------------------------|-----------------------------------|
      | Merge PDFs          | pypdf                              | `writer.add_page(page)`           |
      | Split PDFs          | pypdf                              | one page per file                 |
      | Extract text        | pdfplumber                         | `page.extract_text()`             |
      | Extract tables      | pdfplumber                         | `page.extract_tables()`           |
      | Create PDFs         | reportlab                          | Canvas or Platypus                |
      | Command-line merge  | qpdf                               | `qpdf --empty --pages ...`        |
      | OCR scanned PDFs    | pytesseract                        | convert to image first            |
      | Fill PDF forms      | pdf-lib or pypdf (see forms.md)    | see references/forms.md           |

scenarios:
  - need: Extract text from a scanned PDF that has no embedded text layer.
    context: pdfplumber and pypdf both return empty strings because the PDF is image-only.
    action: |
      Install pytesseract and pdf2image, convert each page to an image, then OCR:
      ```python
      import pytesseract
      from pdf2image import convert_from_path

      images = convert_from_path('scanned.pdf')
      text = ""
      for i, image in enumerate(images):
          text += f"Page {i+1}:\n"
          text += pytesseract.image_to_string(image)
          text += "\n\n"
      print(text)
      ```
    outcome: Extracted plain text per page, ready for downstream parsing or indexing.
  - need: Apply a watermark to every page of a PDF.
    action: |
      Load the watermark PDF's first page, then merge it onto each input page:
      ```python
      from pypdf import PdfReader, PdfWriter

      watermark = PdfReader("watermark.pdf").pages[0]
      reader = PdfReader("document.pdf")
      writer = PdfWriter()
      for page in reader.pages:
          page.merge_page(watermark)
          writer.add_page(page)
      with open("watermarked.pdf", "wb") as output:
          writer.write(output)
      ```
    outcome: A new PDF with the watermark overlaid on every page.
  - need: Extract all images embedded in a PDF.
    action: |
      Use `pdfimages` from poppler-utils:
      ```bash
      pdfimages -j input.pdf output_prefix
      ```
      This writes `output_prefix-000.jpg`, `output_prefix-001.jpg`, etc.
    outcome: One image file per embedded image, suitable for downstream analysis.
  - need: Password-protect a PDF before sharing it.
    action: |
      Re-write the PDF through pypdf with user and owner passwords:
      ```python
      from pypdf import PdfReader, PdfWriter

      reader = PdfReader("input.pdf")
      writer = PdfWriter()
      for page in reader.pages:
          writer.add_page(page)
      writer.encrypt("userpassword", "ownerpassword")
      with open("encrypted.pdf", "wb") as output:
          writer.write(output)
      ```
    outcome: An encrypted PDF that requires the user password to open and the owner password to modify.
  - need: Fill a fillable PDF form.
    action: Read references/forms.md and follow its instructions. Use scripts/extract_form_field_info.py to enumerate fields, then scripts/fill_fillable_fields.py (or scripts/fill_pdf_form_with_annotations.py for non-AcroForm overlays). Validate with scripts/check_fillable_fields.py and scripts/check_bounding_boxes.py.
    outcome: A filled PDF with all required fields populated, validated for correctness.

anti_patterns:
  - Reaching for OCR on a PDF that already has an embedded text layer — try pdfplumber `extract_text()` first; OCR is the fallback for image-only PDFs.
  - Using pypdf to extract tables — pypdf returns flat text without structure; use pdfplumber `extract_tables()` instead.
  - Skipping references/forms.md when filling a form — the helpers in scripts/ are designed to be invoked in the order forms.md prescribes.
  - Loading a large PDF entirely into memory when streaming page-by-page would suffice.
  - Forgetting that `qpdf --pages . 1-5 -- out.pdf` requires the trailing `--` separator before the output filename.
```
