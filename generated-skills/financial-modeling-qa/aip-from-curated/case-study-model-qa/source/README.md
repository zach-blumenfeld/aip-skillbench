# case-study-model-qa: provenance and compile log

## Provenance
- `source/pdf/`: the curated Anthropic `pdf` Agent Skill, copied verbatim: SKILL.md, references/forms.md, references/reference.md, scripts/*, and LICENSE.txt.
- `source/xlsx/`: the curated Anthropic `xlsx` Agent Skill, copied verbatim: SKILL.md, recalc.py, and LICENSE.txt.
- Domain context: the task environment, which is a case-study pack. `background.pdf` is the ModelOff "Roll The Dice" information pack, with the rules for scoring turns and games. `data.xlsx` has a "Formats" legend sheet and a "Data" sheet: header at row 9, columns C:J (Turn number, Game number, Roll 1-6), and 6,000 turns. The container (Ubuntu 24.04) has python3 with pandas 2.2.3, openpyxl 3.1.5, and pypdf 5.1.0, and nothing else: no LibreOffice, pdfplumber, or poppler. Neither task file is copied into the pack. The rules live in `assets/dice_rules.json` and `references/dice-case.md`.
- What the task files showed: one record (turn 15) has been moved out of the table to N37:U37, leaving row 24 blank. A naive `read_excel` + `dropna` loses it. This is why the pack profiles every sheet and sweeps for displaced records.

## Intent
The two curated skills are generic tool guides. The workflow they serve here is: read the rules from a PDF, load the data from a workbook, model it, and answer exam-style questions. The pack compiles that into one graph. It adds the case-specific knowledge the generic skills lack: the scoring rules, the game-combination rule, the workbook traps, and the question-reading pitfalls.

## Step-kind choices
| Step | Kind | Why |
|---|---|---|
| read-inputs | execution | PDF text extraction and workbook profiling are mechanical. A script also surfaces blank rows, displaced cells, and text-stored numbers every time, where an agent glancing at `head()` would miss them. |
| classify-case | decision | Which case this is, and what form the answer takes, are judgments over fixed label sets. `case_type` has a threshold because sending a non-dice case to the dice scorer would give a confidently wrong answer. |
| route-case | router | Branches on `case_type`. |
| confirm-dice-rules | client_task | The agent compares the default rule table against the PDF and the question (a what-if question may change a rule) and emits a rules object. Comparing free text with a table needs reading, and the output is a generated object. |
| score-dice | execution | Turn scoring, distinct-category game maximisation, record recovery, and statistics are all deterministic. They are scripted so no arithmetic is left to free-form reasoning. Rules come in as data (`dice_rules`), so point values and run length can change without code edits. |
| answer-dice-question | client_task | Mapping a natural-language question to the right statistic (denominator, ties, "above" vs "at least") and to an option needs judgment. The step queries the CSVs for anything the summary lacks. |
| model-generic | client_task | Unknown cases have no fixed logic to script. The step carries the loading discipline and the xlsx/pdf guidance. |
| end | end | `answer` + `working`. |

Scripts use only openpyxl and pypdf, plus the stdlib, so they run in the container. pandas is suggested only for the agent's own ad-hoc queries.

## Where the source content went
- xlsx "Requirements for Outputs" (zero errors, preserve templates, colour codes, number formats, assumption placement, formula error prevention, documenting hardcodes): `references/xlsx-guide.md` "Deliverable workbooks", plus an anti-pattern.
- xlsx reading with pandas, the openpyxl and pandas tips, library selection, the verification checklist (column mapping, row offset, NaN, far-right columns, multiple matches): `references/xlsx-guide.md` "Reading and analysing data". The checklist also feeds the generic template's loading step.
- xlsx "use formulas, not hardcoded values", the workflow, creating and editing workbooks, recalc.py usage and output format, code style: `references/xlsx-guide.md`, with `scripts/recalc.py` copied verbatim.
- xlsx "LibreOffice required": kept, but corrected for this container (no `soffice`). The guide says to check the logic in pandas instead.
- pdf text extraction (pypdf quick start, pdfplumber text and tables, pdftotext and its -layout/-f/-l/-bbox-layout options, OCR fallback, encrypted and corrupted PDFs, metadata): `scripts/extract_inputs.py` (pypdf extraction plus a scanned-PDF warning) and `references/pdf-guide.md`.

## Deliberate drops
| Source item | Why dropped |
|---|---|
| pdf: merge, split, rotate, watermark, password-protect, extract images, crop; qpdf, pdftk, and pdf-lib merge/split; pdfjs rendering | PDF manipulation is not part of the case-study QA workflow. Originals stay in `source/pdf/`. |
| pdf: reportlab creation (canvas, platypus, tables) | Nothing in this task produces a PDF. |
| pdf: forms.md and the form scripts (check_fillable_fields, extract_form_field_info, fill_fillable_fields, fill_pdf_form_with_annotations, convert_pdf_to_images, create_validation_image, check_bounding_boxes and its test) | Form filling is out of scope, and `do_not_use_when` says so. Several scripts also need pdf2image or PIL, which the container lacks. |
| pdf reference.md: pypdfium2 rendering and text, JavaScript libraries, pdftoppm and pdfimages options, advanced qpdf encryption and optimisation, batch processing, memory chunking, performance tips, license list | Either not installed in the container or irrelevant to reading a one-page rules pack. The useful fallbacks (pdftotext -bbox-layout, qpdf --check, within_bbox, OCR, decrypt) are in `references/pdf-guide.md`. |
| pdf quick-reference table, "Next steps" | Navigation only, and redundant with the guide. |
| xlsx: three of the four "Source:" example strings | Redundant examples. The format and one example are kept. |
| xlsx frontmatter description and trigger list | Replaced by this pack's description and `trigger_when`. |

## Test notes
- Functional test (in `./scratch`, outside the pack): a synthesized full-length workbook in the same layout. It has a Formats sheet, the Data sheet with titles and the row 9 header, 6,000 turns, two records displaced to other columns with blank rows left behind, an all-sixes turn, a 2-3-4-5 run, and an "End Sheet" label. Both router branches ran to `end`. The scorer recovered both displaced turns. An independent pandas re-implementation matched every turn and game score. The `single_value_counts` toggle and the missing-file error path also behaved.
