# modeloff-case-qa: provenance and compile log

## Provenance

- `xlsx/` — curated Agent Skill `xlsx` (SKILL.md, recalc.py, LICENSE.txt), copied verbatim.
- `pdf/` — curated Agent Skill `pdf` (SKILL.md, references/reference.md, references/forms.md,
  scripts/*.py, LICENSE.txt), copied verbatim.
- Task context (not copied; describes the target runtime): the task statement asks a question
  about `/root/data.xlsx` with background `/root/background.pdf` and wants only the number in
  `/root/answer.txt`. Container: Ubuntu 24.04 `python3` (3.12) with pandas 2.2.3, openpyxl 3.1.5,
  pypdf 5.1.0 only. The sample background is the ModelOff "Roll The Dice" case pack; the sample
  workbook holds 6,000 turns / 3,000 games on sheet `Data` (header at row 9, columns C:J) plus a
  `Formats` style legend.

## Intent

One workflow: read the PDF rules, read the workbook, compute the asked value, write the bare
answer. The two curated skills supply the reading know-how (pypdf extraction; pandas/openpyxl
loading and pitfalls). Domain knowledge for the dice case (rule interpretation, data traps) is
compiled into a script and a reference so another instance of the task (same case, different
rolls or a different question from Q20–Q29) is answered by computation, not by a stored value.

## Component-kind choices

| Step | Kind | Why |
|---|---|---|
| inspect-inputs | execution | PDF text extraction and sheet profiling are deterministic; putting header row, samples, and layout anomalies in state lets the decision judge from facts. |
| classify-case | decision | Recognising the case and the answer form is judgment over a fixed label set (dice/other; integer/decimal/text). Thresholds 0.3 because a wrong case sends the run down the wrong branch and a wrong format can reject or mangle the answer. |
| by-case | router | Branches on `case_type`. |
| score-dice | execution | Every rule (six categories, distinct-category game max, pairing, ties) is deterministic arithmetic; scripting it removes the main error sources (lost displaced record, positional pairing, same-category reuse). Also precomputes the stats behind the typical case questions. |
| answer-dice | client_task | Questions vary in wording; the agent maps the question to a precomputed stat or a short pandas query over the CSVs. |
| general-model | client_task | Unknown cases need the agent to build a model; guided by the adapted xlsx/pdf reference. |
| write-dice-answer / write-model-answer | execution | Normalising a number (separators, units, parentheses, `.0`) and writing the file is deterministic. Two steps share one script because each answer key has one producer per branch and branch-only keys cannot be read after a join. |

Scripts: `inspect_inputs.py`, `dice_model.py`, `write_answer.py` (pandas, openpyxl, pypdf only).

## Verified on the sample files

- The sample workbook hides a trap: turn 15 (game 8) was cut from row 24 and pasted into N37:U37.
  Reading only C:J (or dropna) leaves game 8 with one turn and shifts every positional pairing;
  the odd-vs-even match difference then comes out −29 instead of the correct value. `dice_model.py`
  rebuilds by turn number and reports the repair in `dice_data_issues`. An independent
  re-implementation agreed with the script on the game-score total and the match result.
- No turn in the sample has all six rolls equal, so the "only two numbers" reading (exactly two
  distinct values) does not change results here; the reference says how to recount if needed.

## Completeness check (source line by line)

### xlsx/SKILL.md

| Source item | Where it lives / drop rationale |
|---|---|
| Frontmatter description (create, edit, analyse spreadsheets) | Analysis part → skill description and purpose. Creation/editing → deliberate drop: this task answers a question, it delivers no workbook (`do_not_use_when` routes such tasks away). |
| Zero formula errors in delivered models | Deliberate drop: no workbook is delivered. Error-prevention checks reused for pandas models in `references/xlsx-analysis.md`. |
| Preserve existing templates | Deliberate drop: the input workbook is never modified. |
| Colour-coding standards; number-formatting standards | Deliberate drop: output formatting of delivered models. The `Formats` sheet in case workbooks is identified as a style legend with no data (`xlsx-analysis.md`, Loading). |
| Assumptions placement (separate assumption cells, no hardcodes) | `xlsx-analysis.md` Modelling method step 1; `dice_model.py` reads fixed scores from the background into named values. |
| Formula error prevention (refs, off-by-one, consistent formulas, edge cases, circularity) | `xlsx-analysis.md` Pitfalls and Modelling method steps 3–5. |
| Documentation of hardcodes (Source: … format) | Deliberate drop: applies to hardcoded inputs in delivered workbooks. |
| Reading with pandas (`read_excel`, `sheet_name=None`, head/info/describe) | `xlsx-analysis.md` Loading; `inspect_inputs.py` profiles every sheet. |
| "Use formulas, not hardcoded values" (with examples) | Deliberate drop: rule for workbooks that must stay live; here the result is a single number computed in Python. Its intent (compute from data, never hardcode the answer) → anti-pattern "Hardcoding an answer". |
| Common workflow; recalc.py; LibreOffice requirement; interpreting recalc output; error codes | Deliberate drop: LibreOffice is not in the container and no formulas are written. Noted in `xlsx-analysis.md` ("no LibreOffice, so no recalc.py") and in an anti-pattern. recalc.py kept only in `source/xlsx/`. |
| Creating / editing files with openpyxl (fonts, fills, widths, insert/delete rows, new sheets) | Deliberate drop: no workbook output. |
| Verification checklist: sample references, column mapping (64 = BL), row offset | `xlsx-analysis.md` Loading + Modelling method step 3. |
| Pitfalls: NaN, far-right columns, multiple matches, division by zero, wrong references | `xlsx-analysis.md` Pitfalls. |
| Cross-sheet reference syntax (Sheet1!A1) | Deliberate drop: formula syntax; nothing writes formulas. `dice_model.py` scans all sheets for records. |
| Testing strategy: start small, verify dependencies, edge cases | `xlsx-analysis.md` Modelling method steps 3–5. |
| Library selection (pandas vs openpyxl) | `xlsx-analysis.md` Loading (pandas for analysis, openpyxl `data_only`). |
| openpyxl: 1-based indices, `data_only=True`, never save after `data_only`, `read_only` for large files | `xlsx-analysis.md` Loading; `inspect_inputs.py` uses `data_only` + `read_only`. |
| pandas: dtype, usecols, parse_dates | `xlsx-analysis.md` Loading. |
| Code style (minimal code) / Excel cell comments | Deliberate drop: style guidance; scripts are written minimal. Cell comments apply to delivered workbooks only. |

### pdf/SKILL.md

| Source item | Where it lives / drop rationale |
|---|---|
| pypdf read + extract text (Quick Start) | `inspect_inputs.py` (`PdfReader`, per-page `extract_text`, warnings silenced). |
| Merge, split, metadata, rotate, watermark, password, reportlab creation, qpdf/pdftk, image extraction | Deliberate drop: PDF manipulation and creation are outside the workflow (`do_not_use_when`). Kept in `source/pdf/` and in `references/pdf-reference.md`. |
| pdfplumber text/tables | Not installed in the container; offered only as a fallback via `references/pdf-reference.md`, loaded when the extracted text is empty or garbled. |
| pdftotext CLI | Deliberate drop: poppler not installed; stated in `xlsx-analysis.md`. |
| OCR for scanned PDFs (pytesseract/pdf2image) | `inspect_inputs.py` flags "no extractable text … see pdf-reference OCR notes"; packages are not in the container, so the agent must bootstrap them if ever needed. |
| Quick reference table / Next steps | Pointers only; the relevant pointer (reference.md for troubleshooting) → `references/pdf-reference.md` load condition. |

### pdf/references/reference.md

Mirrored verbatim as `references/pdf-reference.md` (fallback extraction, troubleshooting, encrypted/corrupted PDFs). JavaScript (pdf-lib, pdfjs) and creation sections are irrelevant but left intact rather than edited.

### pdf/references/forms.md and pdf/scripts/* (form filling, bounding boxes, validation images, PDF to images)

Deliberate drop: form filling is out of scope for an analysis question, and several scripts need packages (pdf2image, PIL) absent from the container. Kept verbatim under `source/pdf/`.

### LICENSE.txt files

Kept under `source/`; the frontmatter `license` points to them.

## Functional test log (`aip run` / `aip resume`, inputs kept under ./scratch, not in the skill)

1. Real task files + the task question → `dice` / `integer` → precomputed odd-vs-even stat → end; answer file holds the bare integer, matching an independent re-implementation.
2. Variant dice instance (new rolls, turn 101 moved to another sheet, turn 200 stored as text) + a different question (games scoring 80 or more) → both repairs reported in `dice_data_issues`, answer computed from `dice_games.csv`, matches an independent count.
3. Non-dice case (synthetic loan book, hand-built PDF) → `other` / `integer` → general-model branch → answer given as `$1,134,843`, written as `1134843`.
