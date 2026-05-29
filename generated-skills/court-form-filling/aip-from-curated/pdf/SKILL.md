---
name: pdf
description: Comprehensive PDF manipulation toolkit for extracting text and tables, creating new PDFs, merging/splitting documents, and filling PDF forms (including court forms, government forms, and other fillable or scanned forms). Use when Claude needs to fill out a PDF form, programmatically process, generate, or analyze PDF documents at scale.
license: Proprietary. LICENSE.txt has complete terms
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Programmatically read, write, fill, and transform PDF documents. The body
  encodes the deterministic procedure for filling PDF forms (both fillable
  AcroForm PDFs and scanned/flattened PDFs that require visual annotation),
  because that path requires strict ordering, validation, and coordinate
  arithmetic that scripts execute reliably. General PDF operations (text and
  table extraction, merge/split, create-from-scratch, OCR, watermarking,
  encryption, advanced rendering) are documented in `references/` and loaded
  on demand.

trigger_when:
  - The user asks to fill out, complete, or annotate a PDF form (court form, government form, application, intake form, etc.).
  - The user provides a blank PDF form plus values to enter.
  - The user asks to detect whether a PDF has fillable fields.
  - The user asks to extract text, tables, metadata, or images from a PDF.
  - The user asks to merge, split, rotate, crop, watermark, OCR, or encrypt PDFs.
  - The user asks to generate a new PDF from scratch (reports, invoices, certificates).
  - Any task whose input or expected output is a `.pdf` file.

do_not_use_when:
  - The PDF is already being handled by a more specific domain skill (e.g., a tax-form skill with its own field mapping).
  - The user only needs a one-line `pdftotext` call and has already specified the exact command — defer to general bash.

scope_and_approval: >
  Read-only inspection (detecting fillable fields, extracting field info,
  rendering pages to images, extracting text) is safe to run without
  confirmation. Writing a filled PDF, modifying a PDF, or overwriting an
  existing output path is a write action — write to a new path by default and
  ask before overwriting an existing file. Never discard the original input
  PDF.

steps:
  - name: detect-form-fillability
    description: >
      Determine whether the input PDF has native fillable AcroForm fields.
      Branches the rest of the procedure: AcroForm PDFs use the field-name API
      (faster, more reliable); flat / scanned PDFs require visual analysis
      and text-annotation placement. Run from the skill's directory:
      `python scripts/check_fillable_fields.py <file.pdf>`.
    script: scripts/check_fillable_fields.py
    inputs:
      - name: pdf-path
        type: string
        description: Path to the input PDF.
    outputs:
      - name: has-fillable-fields
        type: boolean
        description: True if AcroForm fields were detected.
    one_of:
      - Fillable AcroForm path — fields are addressable by name. Proceed via `extract-fillable-form-field-info`.
      - Non-fillable / flattened path — no addressable fields. Proceed via `derive-bounding-boxes-visually` and place text annotations on top of the page.

  - name: render-pages-to-images
    description: >
      Render every page of the PDF as a PNG at 200 DPI, downscaled so the
      longest side is at most 1000 px. Required in both branches: AcroForm
      fields still need visual interpretation to assign values, and
      non-fillable forms need page images for bounding-box analysis. Run from
      the skill's directory: `python scripts/convert_pdf_to_images.py <file.pdf> <output_directory>`.
      The script writes `page_1.png`, `page_2.png`, … to `<output_directory>`.
    script: scripts/convert_pdf_to_images.py
    depends_on:
      - detect-form-fillability
    inputs:
      - name: pdf-path
        type: string
      - name: output-directory
        type: string
        description: Existing directory where `page_N.png` files will be written.
    outputs:
      - name: page-image-paths
        type: list[string]
        description: One PNG per PDF page, ordered by page number.

  - name: extract-fillable-form-field-info
    description: >
      Fillable-path only. Produce a JSON list of every fillable field with its
      page, PDF-coordinate rect, type (`text`, `checkbox`, `radio_group`,
      `choice`), and per-type metadata (checkbox `checked_value` /
      `unchecked_value`, radio `radio_options[].value` + `rect`, choice
      `choice_options[].value` + `text`). Run from the skill's directory:
      `python scripts/extract_form_field_info.py <input.pdf> <field_info.json>`.
      See `references/field_info_format.md` for the full output schema. Rects
      are PDF coordinates `[left, bottom, right, top]` with `y=0` at the page
      bottom; convert to image coordinates before comparing against page PNGs.
    script: scripts/extract_form_field_info.py
    depends_on:
      - detect-form-fillability
    inputs:
      - name: pdf-path
        type: string
      - name: field-info-json-path
        type: string
        description: Output path for the field info JSON file.
    outputs:
      - name: field-info-json-path
        type: string

  - name: analyze-fillable-fields
    description: >
      Fillable-path only. For each entry in `field_info.json`, locate the field
      on the corresponding rendered page image (convert the PDF rect to image
      coordinates using each page's image and PDF dimensions) and determine
      the field's purpose from the surrounding visual context (label text,
      adjacent fields, section headings). Produce a mapping from `field_id` to
      a short purpose string plus, for checkboxes/radios/choices, the legal
      value(s) the script will accept. Pure interpretation — no script, the
      agent reasons over the rendered images.
    depends_on:
      - extract-fillable-form-field-info
      - render-pages-to-images
    inputs:
      - name: field-info-json-path
        type: string
      - name: page-image-paths
        type: list[string]
    outputs:
      - name: field-purpose-map
        type: object
        description: '`field_id` → { purpose, allowed_values? }.'

  - name: author-field-values-json
    description: >
      Fillable-path only. Author a `field_values.json` file mapping each field
      the user wants filled to its concrete value. Format (one object per
      field):
      `{ "field_id": "<must match field_info.json>", "description": "<human label>", "page": <int>, "value": <typed value> }`.
      For checkboxes use the field's exact `checked_value` / `unchecked_value`
      string (often `/On` and `/Off`). For radios use one of the
      `radio_options[].value` strings. For choices use one of the
      `choice_options[].value` strings. For text use a plain string.
      `assets/field_values_example.json` is a worked example.
    depends_on:
      - analyze-fillable-fields
    inputs:
      - name: field-purpose-map
        type: object
      - name: user-supplied-data
        type: object
        description: Values the user has provided for the form.
    outputs:
      - name: field-values-json-path
        type: string

  - name: fill-fillable-fields
    description: >
      Fillable-path only. Validate and write. The script verifies every
      `field_id` exists, that the page number matches, and that
      checkbox/radio/choice values are within the field's legal set; on any
      error it exits non-zero and prints the offending field. Fix the
      `field_values.json` and rerun until it succeeds. Run from the skill's
      directory: `python scripts/fill_fillable_fields.py <input.pdf> <field_values.json> <output.pdf>`.
    script: scripts/fill_fillable_fields.py
    depends_on:
      - author-field-values-json
    inputs:
      - name: pdf-path
        type: string
      - name: field-values-json-path
        type: string
      - name: output-pdf-path
        type: string
    outputs:
      - name: filled-pdf-path
        type: string

  - name: derive-bounding-boxes-visually
    description: >
      Non-fillable path only. For each page image, identify every place the
      user is expected to enter data and determine TWO bounding boxes per
      field in IMAGE coordinates `[left, top, right, bottom]` (origin
      top-left): one for the printed label (`label_bounding_box`) and one for
      the entry area where text will be drawn (`entry_bounding_box`). The two
      boxes MUST NOT intersect. The entry box must be tall and wide enough to
      contain the intended text (font size ≤ entry-box height). Common form
      structures and the correct entry-box placement for each:
      `Name: [box]` → entry box to the right of the label, ending at the
      enclosing box edge.
      `Email: ____` → entry box above the line, full line width.
      `____  / Name underneath` → entry box above the line.
      `Please describe: \n ____` → entry box from the bottom of the label
      down to the line, full line width.
      Checkboxes: target the small square `□`, NOT the adjacent label text;
      the entry box covers ONLY the square, the label box covers the word
      ("Yes" / "No").
    depends_on:
      - render-pages-to-images
    inputs:
      - name: page-image-paths
        type: list[string]
    outputs:
      - name: visual-field-analysis
        type: object
        description: Per-field label + entry rects, descriptions, and intended entry text.

  - name: author-fields-json
    description: >
      Non-fillable path only. Encode the visual analysis as a `fields.json`
      with a `pages` array (image dimensions for each page) and a
      `form_fields` array. Each form field carries `page_number`,
      `description`, `field_label`, `label_bounding_box`,
      `entry_bounding_box`, and `entry_text` (`text`, optional `font_size`
      defaulting to 14, optional `font_color` as `RRGGBB` hex defaulting to
      `000000`). Use `X` as the entry text for a checkbox. See
      `assets/fields_example.json` for the worked format.
    depends_on:
      - derive-bounding-boxes-visually
    inputs:
      - name: visual-field-analysis
        type: object
    outputs:
      - name: fields-json-path
        type: string

  - name: check-bounding-boxes
    description: >
      Non-fillable path only. Automated geometric validation: no label/entry
      intersections, no inter-field intersections on the same page, and every
      entry box is at least as tall as its font size (default 14). Run from
      the skill's directory: `python scripts/check_bounding_boxes.py <fields.json>`.
      On any FAILURE message, fix the offending rect in `fields.json` and
      rerun. Do not proceed to filling until the script prints SUCCESS.
    script: scripts/check_bounding_boxes.py
    depends_on:
      - author-fields-json
    inputs:
      - name: fields-json-path
        type: string
    outputs:
      - name: bounding-box-check-pass
        type: boolean

  - name: create-validation-images
    description: >
      Non-fillable path only. For every page that has form fields, overlay
      red rectangles (entry boxes) and blue rectangles (label boxes) on the
      rendered page PNG so they can be inspected. Run once per page from the
      skill's directory:
      `python scripts/create_validation_image.py <page_number> <fields.json> <input_image_path> <output_image_path>`.
    script: scripts/create_validation_image.py
    depends_on:
      - author-fields-json
      - render-pages-to-images
    inputs:
      - name: page-number
        type: integer
      - name: fields-json-path
        type: string
      - name: input-image-path
        type: string
      - name: output-image-path
        type: string
    outputs:
      - name: validation-image-path
        type: string

  - name: inspect-validation-images
    description: >
      Non-fillable path only. Required visual gate. Open each validation image
      and verify: red rectangles cover ONLY input areas and contain NO printed
      text; blue rectangles contain the corresponding label text; for
      checkboxes the red rectangle is centered on the small square and the
      blue rectangle covers the adjacent label word. If any rectangle is
      wrong, fix `fields.json`, regenerate the validation image for that
      page, and re-inspect. Do not proceed until every page is visually
      correct.
    depends_on:
      - check-bounding-boxes
      - create-validation-images
    inputs:
      - name: validation-image-paths
        type: list[string]
    outputs:
      - name: visual-inspection-pass
        type: boolean

  - name: fill-with-annotations
    description: >
      Non-fillable path only. Apply the validated `fields.json` to the input
      PDF as text annotations. The script converts each entry box from image
      coordinates to PDF coordinates using the page dimensions, then writes a
      `FreeText` annotation at that rect. Run from the skill's directory:
      `python scripts/fill_pdf_form_with_annotations.py <input.pdf> <fields.json> <output.pdf>`.
    script: scripts/fill_pdf_form_with_annotations.py
    depends_on:
      - inspect-validation-images
    inputs:
      - name: pdf-path
        type: string
      - name: fields-json-path
        type: string
      - name: output-pdf-path
        type: string
    outputs:
      - name: filled-pdf-path
        type: string

  - name: handle-non-form-pdf-operations
    description: >
      For any non-form task (text/table extraction, merge, split, rotate,
      crop, OCR, watermark, encryption, PDF creation), load
      `references/pdf-general-ops.md` for the canonical recipes. For
      advanced features (pypdfium2 rendering, JavaScript libraries —
      pdf-lib, pdfjs-dist — batch processing, optimization, repair, OCR
      fallback for scanned text), load `references/pdf-advanced.md`. These
      operations do not require the form-filling execution graph.

search_shortcuts:
  - category: Python libraries
    body: >
      pypdf (BSD) — basic read/write, merge, split, metadata, rotate, encrypt.
      pdfplumber (MIT) — layout-aware text and table extraction.
      reportlab (BSD) — generate PDFs from scratch (Canvas + Platypus).
      pypdfium2 (Apache/BSD) — fast rendering via PDFium; preferred for
      large-batch page→image conversion.
      pdf2image + pytesseract — OCR scanned PDFs.
  - category: JavaScript libraries
    body: >
      pdf-lib (MIT) — create and modify PDFs in any JS environment.
      pdfjs-dist (Apache) — Mozilla's PDF.js for rendering and text/annotation
      extraction in the browser or Node.
  - category: CLI tools
    body: >
      pdftotext (poppler) — fastest text extraction, supports `-layout` and
      `-bbox-layout`.
      pdftoppm / pdfimages (poppler) — page-to-image and embedded-image
      extraction.
      qpdf — pages, encryption, optimization, repair.
      pdftk — merge/split/rotate when available.

scenarios:
  - need: Fill a court form PDF that has built-in form fields.
    context: '`check_fillable_fields.py` reports "This PDF has fillable form fields."'
    action: Run `extract_form_field_info.py`, render pages with `convert_pdf_to_images.py`, map field ids to purposes from the rendered images, author `field_values.json`, then run `fill_fillable_fields.py`.
    outcome: A PDF with native form values populated; re-openable and editable in any PDF viewer.
  - need: Fill a scanned court form PDF with no underlying form fields.
    context: '`check_fillable_fields.py` reports the PDF has no fillable fields.'
    action: Render to PNGs, visually identify label and entry bounding boxes, write `fields.json`, run `check_bounding_boxes.py` until SUCCESS, generate validation images with `create_validation_image.py`, inspect each, then run `fill_pdf_form_with_annotations.py`.
    outcome: A PDF with text annotations placed precisely over the printed entry areas.
  - need: Extract every table from a multi-page report PDF into Excel.
    context: PDF has clear ruled tables.
    action: Load `references/pdf-general-ops.md`; use `pdfplumber` to iterate pages and `extract_tables()`; concatenate via pandas; write `.xlsx`.
    outcome: One `.xlsx` workbook with all tables stacked into a single sheet.
  - need: Merge several PDFs into one and rotate page 3.
    action: Load `references/pdf-general-ops.md`; merge with pypdf or qpdf, rotate with `page.rotate(90)` or `qpdf --rotate=+90:3`.
    outcome: Single merged PDF with the requested rotation applied.

anti_patterns:
  - Skipping `check_fillable_fields.py` and assuming fillable vs. non-fillable from the file name or page count — always detect first.
  - Treating PDF coordinates and image coordinates as the same. PDF origin is bottom-left; image origin is top-left. Always convert.
  - For non-fillable forms, letting the entry bounding box overlap the printed label text. The red entry rect MUST be empty of printed characters.
  - For checkboxes, targeting the word "Yes" or "No" instead of the small square. Always target the square.
  - Skipping `inspect-validation-images` because `check_bounding_boxes.py` returned SUCCESS — geometric checks do not verify the boxes are over the right page elements.
  - Hand-editing the output of `extract_form_field_info.py` instead of writing a new `field_values.json` — the extracted info is the source of truth for legal values.
  - Using arbitrary on/off strings for checkboxes. Use the exact `checked_value` / `unchecked_value` from `field_info.json` (typically `/On` and `/Off`).
  - For radio buttons, picking an arbitrary string. Use one of the `radio_options[].value` strings.
  - Ignoring the `fill_fillable_fields.py` validation errors and forcing the run — they catch real mismatches and exit non-zero on purpose.
  - Overwriting the input PDF. Always write to a new output path.
```
