# Provenance: receipt-ocr-to-xlsx

## Sources (copied verbatim into this folder)

| Path | What it is | Used for |
|---|---|---|
| `image-ocr/SKILL.md` | Tesseract/pytesseract OCR skill | OCR engine, PSM modes, preprocessing, multi-pass, confidence, errors, limits |
| `openai-vision/SKILL.md` | GPT-4o vision analysis skill | idea of vision-based reading → replaced by the agent's own image viewing |
| `video-frame-extraction/SKILL.md` | OpenCV frame extraction | not applicable (see drops) |
| `pdf/` (SKILL.md, forms.md, reference.md, scripts/, LICENSE.txt) | PDF toolkit | not applicable except the "OCR scanned docs with pytesseract" pattern |
| `xlsx/` (SKILL.md, recalc.py, LICENSE.txt) | Spreadsheet skill | openpyxl workbook creation, 1-based cells, data_only warning, verification mindset |
| `task-instruction.md` | Task statement the downstream agent receives | output contract, total-keyword hint, exclusions, next-line fallback, comma thousands |

The task environment (Ubuntu 24.04, python3, tesseract-ocr 5.3.4, pytesseract 0.3.13, Pillow 12.0.0,
openpyxl 3.1.5; no pandas, no OpenCV, no LibreOffice, no openai, no network) decided which source
techniques can be used at all.

## Intent

The skill takes a folder of receipt scans and produces a single-sheet xlsx (`results`: filename, date, total_amount).
Testing on the 22 real task images showed that plain Tesseract cannot produce an exact answer alone.
It misreads digits, drops large-font totals, and garbles exclusion words. The skill therefore has three parts:
deterministic OCR plus the rules from the task hint; a required per-image visual verification;
and corrections applied through a validated overrides file, never by hand-editing the xlsx.

## Component kinds (and why)

| Component | Kind | Why |
|---|---|---|
| `receipts.py check` | script | dependency presence is a fixed check |
| `receipts.py extract`: multi-pass OCR, keyword-tier total rules, exclusions, next-line fallback, date regexes/normalisation, cross-pass pooling, review flags | script | all deterministic rules over text: lookup tables (tiers, exclusions), if/then logic, numeric formatting |
| `receipt_check` (date_matches, total_matches, date_legible, total_legible) | decision (4 nouls, one pass per image) | whether the OCR value equals what is printed must be judged from the image; the answer space is yes/no |
| write `overrides.json` | client task | the corrected value must be read off the image by the agent; there is no fixed answer set |
| `receipts.py write` (+ built-in validate) and `validate` | script | output layout, ordering, cell types, null handling, and spec checks are fixed rules |

## Deliberate refinements beyond the hint (documented because they change rule outcomes)

- Keywords are matched on punctuation-collapsed text, so `TOTAL (RM):` counts as `TOTAL RM` (034.jpg).
- A rounding line (`ROUND`, `AFTER ADJ`) is not excluded by tax words alone. `Total After Adj Incl GST 5.90` is the amount paid, while the rule would otherwise pick a tax-summary row (094.jpg).
- `EXCL`/`EXCLUDING` lines are excluded: a pre-tax total is never the answer (077.jpg).
- Column-header lines (`Qty/Price/Description/Item … Amount`) are not tier-4 candidates. Otherwise the next-line fallback returns the first item price.
- The next-line fallback is skipped when digits follow the keyword (`GRAND TOTAL 1000` is an unreadable 10.00, not a cue to read the next line) (052.jpg).
- Within a tier the order of preference is: same-line amount, rounded total, cleanly read number, most passes agreeing, topmost line. The hint does not say which match wins inside a tier.
- Date candidates are matched at every position, because `#19- 18/01/2018` otherwise consumes the date (009.jpg).

## Functional test record (task images, in the task's Docker image)

- `check` OK and `extract` took 44 s for 22 images, all three passes. With the final rules, the script was right on 18/22 rows for both fields
  (all 22 totals but one). The visual check corrected 4 values: 034 date (OCR read 09/08 for 09/03; all passes agreed, so it was unflagged),
  052 total (10.08→10.00), and 071 and 074 dates (unparseable OCR: `19/62/2018`, `2032018`). Before the strict-number preference,
  077's total (21.30 pre-tax instead of the bold `TOTAL: 23.25`) was also caught visually.
- `write` with overrides gave `VALID`, and every row was checked against the image. Error branches tested: impossible override date,
  unknown filename, missing directory, empty directory, malformed workbook (extra sheet, numeric date). Null branch tested
  (override `null` → empty cell; `None` from extract → empty cell).
- Synthetic rule tests: yyyy-mm-dd, `12 MAR 2019`, `Mar 5, 2018`, dd.mm.yy, month-first fallback, phone number not a date;
  `GRAND TOTAL` next-line fallback with `1,234.56`, `TOTAL: RM`, tier precedence, `AMOUNT DUE`, header-line rejection.
- Fresh-agent testing was not done: this session's instructions forbid spawning agents, so the author walked
  every step as the downstream agent would.

## Completeness walk: deliberate drops

### image-ocr/SKILL.md
- Kept: purpose and when-to-use (Trigger When); required libraries (compatibility, `check`); formats (IMAGE_EXTS); language and 300 DPI (reference); basic, confidence, and batch examples (script + reference); PSM table (reference, and the script passes use 3/4/6); preprocessing and advanced variants: grayscale, autocontrast, invert, 2x upscale, thresholds 100/128, sharpen (script + reference); multi-pass strategy (script); Tesseract-not-found and poor or empty output handling (`check`, reference); quality self-check (`validate`); limitations (reference).
- Dropped: the JSON output schema (`success`, `extracted_text`, `confidence`, `metadata.*`, `warnings`). The task's deliverable is the xlsx; `extract.json` keeps per-file text, candidates, and `review_reasons`, which do the job of `warnings`/`confidence` here.
- Changed: multi-pass "combine results" concatenated text. Here candidates are pooled by rule tier and voted on instead, because concatenation duplicates totals and makes "first match" meaningless.
- Dropped: the "under 5 MB, resize if necessary" note. Tesseract has no such limit and the task images are under 1 MB.
- Dropped: version history (not actionable).

### openai-vision/SKILL.md
- Dropped entirely as executable guidance: it needs the `openai` package, an API key, and network, none of which the container provides. Its useful idea, reading text with a vision model, survives as the agent viewing each image itself (decision `receipt_check`). `detail: high` for small text became "zoom in on the region". Per-file try/except became per-pass error tolerance in `extract`. `validate_image` became directory and extension checks. "All images processed" became `validate --img-dir` one-to-one matching.
- Dropped: token cost tables, rate-limit retries, resize-for-API, multi-image comparison, scene/object/colour analysis, and the analysis JSON schema. None applies to this task.

### video-frame-extraction/SKILL.md
- Dropped entirely: there are no video inputs, and OpenCV is not installed. Frame sampling, seeking, codecs, and the frame JSON schema do not apply.

### pdf/ (SKILL.md, forms.md, reference.md, scripts/*)
- Dropped: the inputs are images, not PDFs. pypdf, pdfplumber, reportlab, pdf2image, poppler, and qpdf are not installed. Form filling (all of forms.md and its scripts), merge/split, watermarking, encryption, JS libraries, and the bounding-box validators do not apply. The one relevant pattern, OCR of scanned pages with pytesseract, is what `extract` does.

### xlsx/ (SKILL.md, recalc.py)
- Kept: openpyxl for creating new workbooks (script); 1-based cells; "do not re-save via a data_only load" (gotcha: always regenerate with `write`); the verify-before-delivery loop (`write` validates automatically); concise code style.
- Dropped: zero-formula-errors and recalc.py/LibreOffice. The output has no formulas and LibreOffice is not installed. The "use formulas, not hardcoded values" rule is deliberately reversed here: the oracle compares literal cell values, and the task specifies `total_amount` as a string.
- Dropped: financial-model colour coding, number formats, assumption placement, and source-documentation comments. The task forbids extra content, so styling adds nothing.
- Dropped: pandas reading and writing. pandas is not in the container; openpyxl does everything needed.
- Dropped: template preservation. The output is a new file.

### task-instruction.md
- Every item appears in the body or the script: input/output paths, the single `results` sheet, 3 columns, header row, ordering by filename, ISO date, 2-decimal string total, null on failure, no extra rows/columns/sheets, the keyword tiers in priority order, the exclusion list, the next-line fallback with last number, comma thousands, and the pre-installed libraries.
