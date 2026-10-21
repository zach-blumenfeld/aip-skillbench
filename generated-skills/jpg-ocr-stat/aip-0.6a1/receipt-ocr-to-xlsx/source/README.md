# receipt-ocr-to-xlsx: provenance and compilation notes

## Provenance

Compiled 2026-10-20 from the curated skills under `inputs/skills/`, copied here verbatim:

- `image-ocr/SKILL.md`: Tesseract/pytesseract OCR, preprocessing, PSM modes, multi-pass OCR.
- `xlsx/SKILL.md`, `xlsx/recalc.py`, `xlsx/LICENSE.txt`: spreadsheet creation with openpyxl/pandas, formula recalculation.
- `pdf/` (SKILL.md, reference.md, forms.md, LICENSE.txt, scripts/*): PDF processing and form filling.
- `openai-vision/SKILL.md`: GPT-4o vision analysis and vision-based OCR.
- `video-frame-extraction/SKILL.md`: OpenCV frame extraction.

Also kept: `task-instruction.md`, the task statement the downstream agent receives (output
contract, total-keyword priority hint, exclusion keywords, pre-installed libraries).
Container: ubuntu 24.04, python3 3.12, tesseract-ocr 5.3, pytesseract 0.3.13, Pillow 12.0.0,
openpyxl 3.1.5; no pandas, no LibreOffice, no OpenAI client, no OpenCV, no network
assumed.

## Intent

One workflow: OCR every receipt image in a folder, extract date + total, write
`results` sheet (filename, date, total_amount) to an xlsx, ordered by filename, nulls for
unreadable fields. Built and tuned against the 22 real task images (SROIE-style Malaysian
receipts), checked by eye against the images.

## Component-kind choices

| Step | Kind | Why |
|---|---|---|
| `extract` | execution | OCR, keyword priority, exclusions, amount/date parsing and voting are deterministic rules over text: scriptable, and far faster/more consistent than reading 20+ images by hand. |
| `review-gate` | router | Branches on the script's `needs_review` boolean; no judgment needed. |
| `review` | client_task | Fixing a flagged receipt needs reading the image (the agent is multimodal), which only the agent can do; output is free-form corrections. A decision step cannot produce a date/amount value. |
| `write-reviewed` / `write-auto` | execution | Fixed output contract (one sheet, header, ordering, string types, empty cells for null) plus a re-open verification: purely mechanical. Two steps share one script because each key has exactly one producer and only the reviewed path has `corrections`; the script names its output by which path it is on. |

Design decisions found while testing against the real files:

- Six OCR passes (grayscale; 2x upscale + autocontrast; upscale + binarize at 150; each with
  `--psm 4` and `--psm 6`) with per-pass voting. Single-pass OCR got roughly a quarter of
  the totals or dates wrong (`1000` for `10 00`, `38/02/18`, `19/62/2018`, `17.76` for `17.70`).
- Hint's exclusion list taken literally drops `Total RM Including GST 6%` and `Total After
  Adj Incl GST`, the actual totals, and keeps GST-summary `Total 16.71 0.59` rows. So:
  GST/TAX/SST do not exclude a line that says the amount includes them or a
  rounded/adjusted total; rows after a GST/TAX SUMMARY header are ignored; QTY/ITEM counts,
  CASH, card payments and EXCL lines are excluded too.
- Within a keyword level the rounded/adjusted line, else the last line, wins: the payable
  total follows `Total incl. GST` (`23.26` then bold `TOTAL: 23.25`; `20.98` then `Total RM 21.00`).
- Bare `AMOUNT` is demoted to its own lowest level because item-table headers say AMOUNT.
- The hint's next-line fallback fires only when the keyword line carries no digits at all,
  otherwise a misread `1000` on the GRAND TOTAL line fell through to the CASH line.
- Day-first dates (Malaysian receipts); month-first only when day-first is impossible;
  OCR-confused leading month digit (6/8/9 for 0) repaired; overlapping regex search so
  `#19- 18/01/2018` still yields the date.
- Values are written as strings, nulls as empty cells: the task compares line by line with
  `total_amount` "as a string with exactly two decimal places".

## Completeness check (source -> skill)

task-instruction.md: input path, output path, sheet name, three columns, header row,
filename ordering, ISO date, two-decimal string, null on failure, no extra
rows/columns/sheets -> `write_xlsx.py` + write-step descriptions + anti_patterns. Keyword
priority, exclusion list, next-line fallback, comma thousands -> `extract_receipts.py`
(LEVELS, EXCLUDE, next-line, AMOUNT_RE), `extract` description, `assets/review.md`.
Pre-installed libraries -> `requires`, anti_patterns.

image-ocr/SKILL.md:
- pytesseract `image_to_string`, PIL -> extract script.
- Input formats JPG/JPEG/PNG/WEBP -> IMAGE_EXTS (plus BMP/TIFF).
- Language `eng` default -> implicit default; non-English not applicable (dropped, below).
- PSM modes list and when to use -> passes use 4 and 6; list in references/receipt-ocr-notes.md.
- Preprocessing: grayscale, autocontrast, sharpen, invert, upscale, threshold (100/128) -> passes use grayscale/autocontrast/upscale/threshold; the rest in the re-OCR recipe in references.
- Multi-pass strategy (several PSMs x variants) -> extract script; it votes instead of concatenating, since concatenated text cannot be parsed for one value.
- Batch processing sorted directory -> extract script sorts.
- Error handling: Tesseract not found -> `requires.tools: tesseract` (client checks) and the reference; poor quality / empty output -> multi-pass + review flags; corrupt image -> `ocr_pass` returns "" so the file gets null + flag instead of crashing.
- Confidence (image_to_data averages) -> replaced by inter-pass agreement, which flagged the actually wrong receipts in testing; the per-word confidence dict is dropped (below).
- Limitations (handwriting, degradation) -> references "Limits"; review rule "null only when not legible".
- Quality self-check (valid JSON, fields present) -> the runtime validates script stdout against declared outputs.

xlsx/SKILL.md:
- openpyxl Workbook / `ws.append` / `wb.save`, sheet title -> write_xlsx.py.
- Re-open to verify -> write_xlsx.py `verify`.
- "Study and match existing templates" -> not applicable (new file); "zero formula errors" -> no formulas are written, so trivially met.
- Formula verification checklist "1-indexed rows, off-by-one" -> header row then data, verified by content comparison.

## Deliberate-drop log

| Source item | Why dropped |
|---|---|
| image-ocr JSON output schema (success/confidence/metadata/warnings per image) | The task's output is an xlsx; per-file evidence is kept in `records` (votes, review_reasons) instead. |
| image-ocr average-confidence high/medium/low thresholds (80/50) | Tesseract word confidence did not track wrong totals on these receipts; inter-pass agreement is used to flag. |
| image-ocr multi-language (`eng+fra+deu`), 300 DPI / 5 MB guidance | Task text is English + digits; images are given as-is. |
| image-ocr version history | Background. |
| xlsx financial-model rules (color coding, number formats, assumptions, hardcode sourcing) | No financial model; values must be plain strings for a line-by-line comparison. |
| xlsx "use formulas, not hardcoded values" and recalc.py / LibreOffice | No calculations in the sheet; LibreOffice is not in the container. |
| xlsx pandas read/analyse examples | pandas is not installed in the container; openpyxl suffices. |
| xlsx code-style guidance | Applied in the scripts; not procedure content. |
| pdf skill (pypdf, pdfplumber, reportlab, qpdf, forms, scripts) | Inputs are images, not PDFs. Its scanned-PDF OCR recipe (pytesseract on rendered pages) duplicates image-ocr. |
| openai-vision skill (GPT-4o API, detail levels, token costs, retries) | No OpenAI client/network in the container; the agent's own vision covers the review step. Its guidance "use high detail for text" maps to "open the full image" in review.md. |
| video-frame-extraction skill (OpenCV) | No video input; OpenCV not installed. |
