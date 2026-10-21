---
name: receipt-ocr-to-xlsx
description: Extract the date and total amount from a folder of scanned receipt images (JPG/PNG, mostly Malaysian RM receipts) with Tesseract OCR and write them to an Excel sheet with one row per file. Use for receipt / invoice OCR tasks that ask for filename, ISO date (YYYY-MM-DD) and a two-decimal total_amount string in an xlsx (e.g. stat_ocr.xlsx with a "results" sheet), including GRAND TOTAL / TOTAL RM keyword priority, subtotal/tax/change exclusion, and null for fields that cannot be read.
metadata:
  aip-version: "0.6a1"
---

# AIP runtime — format 0.6a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the one JSON object a run carries. Each step declares the keys it reads as `inputs`; `execution` and `client_task` steps declare the keys they add as `outputs`, and a `decision` adds one key per question.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the procedure's result.

## Execution

The state starts as the start step's `inputs` and flows along `inputs_to`; each step adds its outputs to it. Every key is produced by exactly one step, so keys accumulate and nothing is overwritten. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. A step sees only those keys: give it its declared `inputs` and nothing else from the state. You have the final say at every step.

- **`execution`**: before the first one, check that this machine has everything `requires` names (the interpreter at its minimum version, the packages, the tools); if anything is missing, stop and name all of it. Run `script` from its folder, launched with the step's `command` when it has one and `python <script>` otherwise, with one JSON object on stdin, `{"state": <the step's inputs>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout holding exactly the step's `outputs`; add them to the state. A non-zero exit, or output missing a declared key, fails the step: stop there and report it rather than doing the step by hand.
- **`decision`**: answer each question from the step's inputs, and from the run so far only when the step sets `history: true`. Each answer collapses to one value under its question name and is added to the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the step's inputs, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the step's `outputs`; add them to the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. Those keys are the procedure's result.

```yaml
purpose: >
  Turn a folder of scanned receipt images into one Excel sheet "results" with columns
  filename, date (YYYY-MM-DD) and total_amount (string with exactly two decimals), one
  row per image ordered by filename, null where a field cannot be read. A script OCRs
  every image in six Tesseract passes (grayscale, 2x upscale + autocontrast, upscale +
  binarize; each with --psm 4 and --psm 6), extracts date and total from each pass and
  votes; receipts whose passes disagree or lack a value are flagged, and you correct
  only those by looking at the image; a second script writes and verifies the workbook.

trigger_when:
  - A task gives a directory of scanned receipt or invoice images and asks for each one's date and total amount in a spreadsheet.
  - The task names /app/workspace/dataset/img as the input and /app/workspace/stat_ocr.xlsx (sheet "results", columns filename, date, total_amount) as the output.
  - Receipt OCR with keyword-priority total detection (GRAND TOTAL, TOTAL RM, TOTAL AMOUNT, TOTAL) and subtotal/tax/change exclusions.

do_not_use_when:
  - The documents are PDFs with a text layer (extract the text directly instead of OCR).
  - The task wants line items, merchant names, or any column beyond filename, date and total_amount.
  - The output must contain live Excel formulas or financial-model formatting.

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - pytesseract
    - Pillow
    - openpyxl
  tools:
    - tesseract

steps:
  - name: extract
    kind: execution
    description: >
      OCR every image file (.jpg .jpeg .png .webp .bmp .tif .tiff) in image_dir, sorted by
      name, and extract one date and one total per receipt. Total = last amount on the
      first line of the most specific keyword level present: 1 GRAND TOTAL; 2 TOTAL RM /
      TOTAL: RM / TOTAL (RM); 3 TOTAL AMOUNT; 4 TOTAL, TOTAL DUE, AMOUNT DUE, BALANCE DUE,
      NETT/NET TOTAL; 5 bare AMOUNT. Lines with SUBTOTAL / SUB TOTAL / SUB-TOTAL, TAX, GST,
      SST, DISCOUNT, CHANGE, CASH TENDERED, CASH, card names, QTY / ITEM counts or EXCL are
      skipped, except that a line saying the amount INCLUDES GST/tax, or a rounded /
      adjusted total, is kept. Within a level the last rounded/adjusted line wins, else the
      last line (the payable total follows intermediate ones); rows after a GST/TAX
      SUMMARY header are ignored. If the keyword line has no number, the last number on
      the next non-empty line is used. Amounts accept 1,234.56, 12,30, 12 .30 and a
      point-less "10 00" at line end. Dates accept dd/mm/yy(yy), dd-mm-yyyy, dd.mm.yyyy,
      yyyy-mm-dd, 29 DEC 2017 and DEC 29, 2017, read day-first (Malaysian receipts),
      years 2000-2035, and lines labelled Date count double in the vote. A file is
      flagged when no date/total is found, fewer than 60% of date votes or 75% of total
      votes agree, the total came only from a weak keyword in under three passes, or only
      from the next-line fallback. Takes about 1-3 s per image.
    inputs:
      - name: image_dir
        type: string
        description: Folder holding the receipt images (in the task container /app/workspace/dataset/img).
      - name: output_path
        type: string
        description: Where the xlsx goes (in the task container /app/workspace/stat_ocr.xlsx). Not used by this step; carried to the writer.
    script: scripts/extract_receipts.py
    timeout: 1800
    outputs:
      - name: records
        type: list[*]
        description: One object per image, sorted by filename, with filename, date (ISO or null), total_amount ("12.30" or null), total_keyword_level, total_votes, date_votes and review_reasons.
      - name: flagged
        type: list[*]
        description: Filenames whose review_reasons is non-empty.
      - name: needs_review
        type: boolean
        description: True when at least one file is flagged.
    inputs_to: review-gate

  - name: review-gate
    kind: router
    description: Flagged receipts get a visual review before writing; a clean batch is written as extracted.
    branch_on: needs_review
    branches:
      "true": review
      "false": write-auto

  - name: review
    kind: client_task
    description: >
      Look at each flagged image and supply the correct date and total, applying the same
      keyword rules a human would; leave unflagged records alone. Do not edit records
      directly or re-run the whole extraction: answer with corrections only.
    inputs:
      - name: image_dir
        type: string
      - name: flagged
        type: list[*]
      - name: records
        type: list[*]
    template: assets/review.md
    references:
      - path: references/receipt-ocr-notes.md
        description: OCR misread patterns seen on these receipts and targeted re-OCR recipes. Load when you cannot view an image or the image itself is hard to read.
    outputs:
      - name: corrections
        type: list[*]
        description: One object per flagged file with filename, date ("YYYY-MM-DD" or null) and total_amount ("12.30" or null).
    inputs_to: write-reviewed

  - name: write-reviewed
    kind: execution
    description: >
      Apply the corrections over the extracted records, normalise (ISO dates that are real
      calendar days, totals as two-decimal strings without currency or thousands
      separators, anything else becomes null), write output_path with exactly one sheet
      "results", header row filename/date/total_amount, one row per image sorted by
      filename, every value a string and nulls as empty cells; then re-open the file and
      fail if sheets, columns, order or content differ.
    inputs:
      - name: records
        type: list[*]
      - name: corrections
        type: list[*]
      - name: output_path
        type: string
    script: scripts/write_xlsx.py
    outputs:
      - name: final_rows
        type: list[*]
        description: The rows written, as filename/date/total_amount objects.
    inputs_to: end

  - name: write-auto
    kind: execution
    description: Same writer and verification as write-reviewed, for a batch with nothing flagged (no corrections).
    inputs:
      - name: records
        type: list[*]
      - name: output_path
        type: string
    script: scripts/write_xlsx.py
    outputs:
      - name: final_rows_auto
        type: list[*]
        description: The rows written, as filename/date/total_amount objects.
    inputs_to: end

  - name: end
    kind: end
    description: The workbook at output_path holds the results; records carry the per-file extraction evidence.
    inputs:
      - name: output_path
        type: string
      - name: records
        type: list[*]

anti_patterns:
  - Hardcoding dates or totals for known filenames; every value must come from the images given.
  - Taking a subtotal, GST/tax amount, cash tendered, change, item count, or a GST-summary "Total" row as the total.
  - Taking "Total incl. GST" when a rounded total (Total Rounded, Total After Adj, final TOTAL) follows it.
  - Reading dd/mm dates month-first, or writing dates as Excel date cells or totals as numbers (10.0 instead of "10.00").
  - Adding an index column, extra sheets, a summary row, or leaving the default sheet name instead of "results".
  - Writing "null", "None" or "N/A" text for a missing value instead of an empty cell.
  - Guessing a value that is not legible on the image instead of leaving it null.
  - Using a vision API or extra packages the container does not have; Tesseract, pytesseract, Pillow and openpyxl are what is installed.
```
