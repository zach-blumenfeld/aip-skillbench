Review the receipts the OCR extractor flagged and correct their date and total.

Image folder: {image_dir}
Flagged files: {flagged}

Extractor records (all files; `review_reasons` says why a file was flagged,
`total_votes` / `date_votes` show what the OCR passes read):
{records}

For each flagged file only:

1. Open the image itself (`{image_dir}/<filename>`) and read it. Viewing the image is
   the authority; the votes are just hints. If you cannot view images, re-OCR just the
   bottom half (totals) or top third (date) with pytesseract: crop, upscale 2-3x,
   grayscale + autocontrast, try `--psm 4` and `--psm 6`.
2. Date: the receipt's transaction date as `YYYY-MM-DD`. Receipts are Malaysian:
   day-first (`18/03/18` is 2018-03-18; two-digit years are 20xx). If several dates
   are printed (date + print/closed date), they normally agree; use the one labelled
   Date or printed with the time.
3. Total: the final amount the customer pays, two decimals, no currency, no thousands
   separator (`1,234.56` -> `"1234.56"`). Find it by keyword priority:
   `GRAND TOTAL` > `TOTAL RM` / `TOTAL: RM` > `TOTAL AMOUNT` > `TOTAL`, `AMOUNT`,
   `TOTAL DUE`, `AMOUNT DUE`, `BALANCE DUE`, `NETT TOTAL`, `NET TOTAL`.
   Never take subtotal, sub total, tax/GST/SST amounts, discount, change, cash
   tendered/paid, item counts, or rows of a GST/tax summary table. A "Total incl. GST"
   line is a total. When a rounding adjustment follows, the rounded total
   (`Total Rounded`, `Total After Adj`, a final bold `TOTAL:`) is the answer. If the
   keyword and its amount are on separate lines, the amount is the last number on the
   next line / in the amount column beside it. Cross-check: the total usually equals
   payment minus change, and subtotal + tax + rounding.
4. Use `null` for a field only when it is genuinely not legible on the image.

Answer with `corrections`: a list with one object per flagged file, holding the keys
`filename`, `date` ("YYYY-MM-DD" or null) and `total_amount` ("12.30" or null).
Include both fields even when one of them was already right.
