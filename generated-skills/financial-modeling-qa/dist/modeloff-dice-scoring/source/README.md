# Source and provenance — modeloff-dice-scoring

## Inputs

- `xlsx/` — curated Agent Skill "xlsx" (SKILL.md, recalc.py, LICENSE.txt), copied verbatim.
- `pdf/` — curated Agent Skill "pdf" (SKILL.md, references/reference.md, references/forms.md, references/LICENSE.txt, scripts/*.py), copied verbatim.
- Task statement (not copied; it belongs to the task): analyze `/root/data.xlsx` with background `/root/background.pdf` (ModelOff 2016 Round 1 Section 3, "Roll The Dice"), answer a question such as "odd games = Player 1, even games = Player 2, matched game 1 vs 2, 3 vs 4 …; (P1 match wins) − (P2 match wins)", write only the number to `/root/answer.txt`.
- Task container: Ubuntu 24.04, python3, pandas 2.2.3, openpyxl 3.1.5, pypdf 5.1.0. No LibreOffice, pdfplumber, poppler, qpdf, OCR.

## Intent

The two curated skills are general file toolkits. The workflow they jointly describe here is: read rules from a PDF, analyze a large workbook with pandas/openpyxl, compute a number. The distilled skill specializes that to the dice case so the scoring logic is scripted and tested, while carrying over the file-handling knowledge that applies in the container.

Findings from the real input files that shaped the skill:
- PDF text extracts cleanly with pypdf (1 page; harmless "wrong pointing object" warnings). It defines 6 scoring categories, 2 turns per game, no category reused per game.
- Workbook: sheets `Formats` (style legend, ignore) and `Data`. Header at row 9 (`Turn number`, `Game number`, `Roll 1..6`, columns C–J), 6000 turns / 3000 games, integer values, no formulas.
- Planted defect: Excel row 24 (turn 15) is blank and its eight values are at `Data!N37:U37`. A naive loader silently drops game 8 and gets a different match result. The loader recovers it and the data-report decision forces a check.
- No turn has all six rolls equal, so the "Only two numbers" single-value interpretation is moot on this file but kept as a decision for other instances.
- Result cross-checked against an independent pandas implementation in the session (same game totals and match tally).

## Component kinds

| Component | Kind | Why |
|---|---|---|
| Extract PDF text | execution (`scripts/extract_pdf_text.py`) | Deterministic; pypdf is the only PDF library in the container. |
| Rules match defaults / question scope | decision (noul + choice) | Comparing prose rules to the encoded table and classifying the question need judgment, but the answer space is fixed; answers drive script flags and step 5. |
| Load, repair, score turns, score games, tally matches | execution (`scripts/dice_model.py`) | All rules are deterministic formulas, thresholds, and an exhaustive 30-pair search; table location and displaced-row recovery are rule-based. One script because the steps share the loaded data. |
| Data trustworthy / two-numbers single | decision (noul ×2) | Whether residual stray cells or gaps are real defects, and how to read the rule wording, need judgment; answers map to a repair path or a flag. |
| Map question to output | client task, with a lookup table first | Common questions are a table lookup in the body; free-form questions need the agent to write a small pandas query. |
| Write answer | instruction | Format rule only (number only). |

## Completeness check — source items and where they live

xlsx/SKILL.md
- Zero formula errors; preserve templates; color coding; number formatting; assumptions placement; hardcode documentation; formula-not-hardcode rule; formula verification checklist → condensed in `references/reading-xlsx-pdf.md` "If you write a model workbook". The deliverable is a number in answer.txt, so the full financial-model styling rules (colors RGB values, $#,##0 formats, year-as-text, 0.0x multiples, parentheses for negatives, source-comment format) are a **deliberate drop**: no workbook is delivered.
- pandas reading (`read_excel`, `sheet_name=None`, head/info/describe, dtype, usecols, parse_dates) → reference "pandas".
- openpyxl (1-based indices, `data_only=True`, the save-loses-formulas warning, `read_only`) → reference "openpyxl" and SKILL.md gotchas.
- Pitfalls: NaN handling, far-right columns, multiple matches, column-letter mapping, row offset → reference "pandas".
- recalc.py / LibreOffice workflow and its JSON output → **deliberate drop**: LibreOffice is not in the container and the input has no formulas; SKILL.md gotcha says not to recalc. recalc.py stays in `source/xlsx/`.
- Creating/editing workbooks with openpyxl styling (Font, PatternFill, column widths, insert/delete rows) → **deliberate drop**: not needed to answer.
- Code style guidance (minimal code, few prints) → **deliberate drop**: generic.

pdf/SKILL.md, references/reference.md
- pypdf read + extract_text → `scripts/extract_pdf_text.py`, reference "pypdf". Encrypted-PDF decrypt → both.
- Metadata → reference "pypdf".
- pdfplumber text/tables, pdftotext, pypdfium2, pdf.js, poppler, OCR (pytesseract/pdf2image) → **deliberate drop** except a note listing them as unavailable: none are installed in the container; the background PDF extracts cleanly with pypdf; scanned-page detection is in the script.
- Merge/split/rotate/watermark/crop/encrypt, reportlab creation, pdf-lib, qpdf, batch processing, performance tips → **deliberate drop**: no PDF is produced or modified.

pdf/references/forms.md and scripts (check_fillable_fields, extract_form_field_info, fill_fillable_fields, convert_pdf_to_images, create_validation_image, check_bounding_boxes(+test), fill_pdf_form_with_annotations) → **deliberate drop**: form filling is outside this workflow; pdf2image/PIL are not installed. Kept verbatim in `source/pdf/`.

LICENSE.txt files → kept in `source/` only.

Task-specific rules (from the background PDF, encoded rather than copied because the PDF is a task input):
- 6 categories with formulas and fixed scores 30/40/50, run of 4 → `dice_model.py score_turn`, SKILL.md table, override flags.
- 2 turns/game, best combined score, no category used twice → `best_game` (all 30 ordered pairs of distinct categories).
- 6,000 turns / 3,000 games → validated by the loader (missing turns, games without two turns).
- Odd = Player 1, even = Player 2, matched 1v2, 3v4 → `matches.csv`, `matches_odd_vs_even`; ties count for nobody.
