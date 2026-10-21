---
name: receipt-ocr-to-xlsx
description: Extract the transaction date and final total amount from a folder of scanned receipt images (JPG/PNG) with Tesseract OCR plus visual verification, and write them to a single-sheet Excel file (filename, date as YYYY-MM-DD, total_amount as a 2-decimal string, null when unreadable). Use for receipt/invoice OCR batch jobs, "read all receipt images and write date and total to xlsx", SROIE-style Malaysian receipts, GRAND TOTAL / TOTAL RM keyword extraction.
compatibility: Python >= 3.8; pip packages pytesseract, Pillow, openpyxl; tesseract-ocr binary on PATH (English traineddata). No network, no LibreOffice, no pandas needed.
---

# Receipt OCR → date + total → xlsx

## Trigger When

- A task gives a directory of scanned receipt / invoice images and asks for the date and the total amount of each one.
- The output is a spreadsheet (xlsx) with one row per image, ordered by filename, often compared cell by cell against an oracle.
- Any batch "OCR images then pull structured fields into Excel" job where Tesseract is the installed OCR engine.

## Purpose

Turns a folder of receipt images into a validated `results` sheet with `filename`, `date`, and `total_amount`. A script does the deterministic part: multi-pass Tesseract OCR, the keyword-priority rules for picking the total, date parsing and normalisation, and writing and validating the xlsx. Raw Tesseract on real receipt scans misreads digits (`15.u00`, `92:80`, `19/62/2018`), misses large-font totals, and garbles exclusion words (`GST` → `ast`). So the skill adds a required visual check of every image, and corrections go in as overrides.

## Inputs and outputs

- `IMG_DIR`: the image folder named in the task (e.g. `/app/workspace/dataset/img`).
- `OUT_XLSX`: the output file named in the task (e.g. `/app/workspace/stat_ocr.xlsx`).
- `/tmp/receipts/`: scratch folder for intermediate files (any folder outside the skill and the output folder works; adjust the commands if you change it). This keeps the output folder holding only the xlsx.

Run every command from this skill's folder.

## Procedure

- [ ] 1. Check dependencies: `python3 scripts/receipts.py check`. If it prints `MISSING:`, name everything it lists and install it (`pip3 install --break-system-packages pytesseract Pillow openpyxl`, `apt-get install -y tesseract-ocr`) before going on.
- [ ] 2. Extract: `mkdir -p /tmp/receipts && python3 scripts/receipts.py extract IMG_DIR /tmp/receipts/extract.json`
- [ ] 3. Verify every image (decision `receipt_check` below). Write corrections to `/tmp/receipts/overrides.json` (client task below).
- [ ] 4. Write and validate: `python3 scripts/receipts.py write /tmp/receipts/extract.json OUT_XLSX --overrides /tmp/receipts/overrides.json`. Leave out `--overrides` only when there are no corrections. The command must end with `VALID:`. If it prints `error:` or `VALIDATION FAILED`, fix what it names and run it again.
- [ ] 5. Optional re-check of the finished file: `python3 scripts/receipts.py validate OUT_XLSX --img-dir IMG_DIR`

### Step 2: `extract` (script)

This step reads every image in `IMG_DIR` (.jpg .jpeg .png .webp .tif .tiff .bmp, sorted by name). It runs three Tesseract passes per image in parallel: raw image with default PSM 3, grayscale + autocontrast with `--psm 4`, and the same upscaled 2x when small with `--psm 6`. It then applies these rules:

- **Total, by keyword priority** (from the task author's hint). Keywords are matched case-insensitively, with punctuation collapsed, so `TOTAL (RM):` counts as `TOTAL RM`:
  1. `GRAND TOTAL`
  2. `TOTAL RM`, `TOTAL: RM`
  3. `TOTAL AMOUNT`
  4. `TOTAL`, `AMOUNT`, `TOTAL DUE`, `AMOUNT DUE`, `BALANCE DUE`, `NETT TOTAL`, `NET TOTAL`
  - Skip lines containing `SUBTOTAL`, `SUB TOTAL`, `TAX`, `GST`, `SST`, `DISCOUNT`, `CHANGE`, or `CASH TENDERED`. Also skip `EXCL`/`EXCLUDING` lines, because a pre-tax total is never the answer. One exception: a rounding line (`ROUND`, `AFTER ADJ`) is kept even if it contains a tax word, since it holds the amount actually paid. Column-header lines (`Qty … Price … Amount`) are skipped too.
  - Take the last number on the line, and accept comma thousands (`1,234.56`). If the keyword line has no number, take the last number on the next line. The script does not apply this fallback when digits follow the keyword, because then the amount is on the line but unreadable.
  - Pool candidates from all passes and keep the most specific tier. Within that tier, prefer a same-line amount, then a rounded total, then a cleanly read number, then the value most passes agree on, then the topmost line.
- **Date**: dd/mm/yyyy, dd-mm-yy, dd.mm.yy, yyyy-mm-dd, `12 MAR 2019`, `Mar 5, 2018`. Day-first; month-first is used only when day-first is impossible. Two-digit years become 20yy. The year must fall between 2000 and next year. A line labelled `Date` wins; otherwise the first valid date is used. Output is ISO `YYYY-MM-DD`.

It prints a table (`filename  date  total  review`) and writes `/tmp/receipts/extract.json`. Each result there carries `date`, `total_amount`, `total_line`, `review_reasons`, per-pass candidates, and `ocr_text_primary`. A `None` means no value was found.

### Step 3: `receipt_check` (decision, one pass per image)

Input: one image, opened with your image-viewing tool (e.g. Read on the .jpg), plus that file's row from the extract table and its `review_reasons` and candidates in `extract.json`. Check **every** image, not only the flagged ones. In testing, an unflagged row had a wrong date: all three passes misread `09/03/2018` as `09/08/2018`.

```yaml
date_matches:
  type: noul
  instructions: Is the script's date exactly the receipt's transaction date, as printed?
  criteria:
    true: Same day, month and year as the transaction date line ("Date:", or the date beside the time). Read dd/mm day-first.
    false: Any digit differs, the script gave None while a date is printed, or the script picked a non-transaction date while the transaction date is printed elsewhere.
total_matches:
  type: noul
  instructions: Is the script's total exactly the receipt's final payable total under the keyword priority above?
  criteria:
    true: Equals, to the cent, the amount on the highest-priority total line that is not a subtotal, tax, GST, discount, change or cash-tendered line. When a rounded total exists, it equals the rounded total.
    false: Any digit differs, it is a subtotal, pre-tax, tax-summary, cash or change amount, or it is None while a total is printed.
date_legible:
  type: noul
  instructions: Only when date_matches is false. Can you read the transaction date on the image with confidence? (true when date_matches is true.)
  criteria:
    true: Day, month and year are all readable.
    false: Missing, torn, or too faded to read any part with confidence.
total_legible:
  type: noul
  instructions: Only when total_matches is false. Can you read the final total with confidence? (true when total_matches is true.)
  criteria:
    true: Every digit of the final total is readable.
    false: Missing or unreadable.
```

Missing a misread is the costly error. Reconsider any close call that leans toward `date_matches: true` or `total_matches: true`, especially when `review_reasons` is non-empty. Zoom in on the relevant region if your viewer allows it.

Which total to read:
- `GRAND TOTAL` beats `TOTAL RM` / `TOTAL: RM`, which beats `TOTAL AMOUNT`, which beats plain `TOTAL`, `NET TOTAL`, `AMOUNT DUE`, and the like.
- `Total Rounded` / `Total After Adj` / `Rounded Total` beats the unrounded total.
- Tax-summary rows at the bottom (`Total 16.71 0.99`) are never the total.
- A big bold `TOTAL:` line is often missed by OCR. Read it from the image.

Which date to read: the transaction date. If a print date or closed date is also shown, prefer the line labelled `Date`. On fuel receipts, the `Date Time Num OPT` header has the date on the next line (`18/03/18` → `2018-03-18`).

### Step 3 (cont.): write `overrides.json` (client task)

For each image where `date_matches` or `total_matches` is false, add an entry with only the wrong field(s). Use the value read from the image, or `null` when the matching `*_legible` is false:

```json
{
  "034.jpg": {"date": "2018-03-09"},
  "052.jpg": {"total_amount": "10.00"},
  "071.jpg": {"date": "2018-02-19", "total_amount": null}
}
```

`write` rejects unknown filenames, impossible dates, and non-numeric amounts. Amounts are reformatted to 2 decimals (`1,234.5` → `1234.50`). Never put in a value you cannot see on the image: `null` is the specified result for a field that cannot be extracted.

### Step 4: what `write` produces

`write` produces exactly one sheet named `results`. Row 1 holds `filename | date | total_amount`, followed by one row per image ordered by filename. `date` and `total_amount` are text cells (`"2018-03-09"`, `"47.70"`), and null fields are empty cells. There are no other columns, rows, sheets, formulas, or styling. The command then validates the file and lists any violation.

## Gotchas

- The task's paths are container paths. Use them exactly as given, and keep `extract.json` and `overrides.json` out of the output folder.
- Never type numbers into the xlsx by hand, and never re-save it with another tool. Always regenerate with `write`, so the text-cell types and ordering stay correct.
- Do not compute totals as formulas or from line items. The answer is the printed final total.
- Extraction takes about 2 s per image (3 passes, parallel across CPUs). If time is very tight, `--workers N` controls parallelism.
- If you cannot view images at all, accept the script's values. For rows where `review_reasons` contains "no date found" or "no total found", the script already leaves the cell null.
- Read [references/ocr-tuning.md](references/ocr-tuning.md) only if you want to re-OCR one stubborn image yourself (PSM modes, preprocessing variants, confidence data).
