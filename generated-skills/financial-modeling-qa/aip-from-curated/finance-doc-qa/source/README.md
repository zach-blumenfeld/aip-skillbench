# Source materials and compilation notes

## Provenance

Compiled from two curated Agent Skills that ship with the SkillsBench task `financial-modeling-qa`:

- `xlsx/` — vendored verbatim from `vendor/skillsbench/tasks/financial-modeling-qa/environment/skills/xlsx/`
  - `SKILL.md` — spreadsheet creation/editing/analysis with pandas and openpyxl
  - `recalc.py` — LibreOffice-driven formula recalculation
  - `LICENSE.txt` — proprietary license
- `pdf/` — vendored verbatim from `vendor/skillsbench/tasks/financial-modeling-qa/environment/skills/pdf/`
  - `SKILL.md` — PDF text/table extraction, creation, merging, splitting, forms
  - `scripts/` — form-filling and bounding-box utilities
  - `references/reference.md` — advanced pypdfium2, reportlab, pdf-lib, qpdf, poppler-utils patterns
  - `references/forms.md` — fillable-form workflow
  - `references/LICENSE.txt` — proprietary license

The task environment (`vendor/skillsbench/tasks/financial-modeling-qa/environment/Dockerfile`) ships:

- Ubuntu 24.04
- `python3` with `pandas==2.2.3`, `openpyxl==3.1.5`, `pypdf==5.1.0`

Nothing else. LibreOffice, pdfplumber, pypdfium2, reportlab, pdf-lib, qpdf, poppler-utils, and pytesseract are **not** installed. Every script in `scripts/` and every recipe in `references/` respects that constraint.

## Task shape driving the compilation

The task hands the agent (see `../vendor/.../instruction.md`):

1. A question in natural language.
2. `/root/data.xlsx` — a data workbook.
3. `/root/background.pdf` — a rules/context document.
4. Instructions to write a single number to `/root/answer.txt`.

The verifier (`tests/test_outputs.py`) accepts anything matching `^-?\d+(\.\d+)?$` within a tight numeric tolerance. So the compiled skill is a "read PDF + read XLSX + derive one number + write it" pipeline rather than a spreadsheet-authoring skill.

## Step-kind choices

| Step | Kind | Why |
|---|---|---|
| `extract-background` | `execution` | Deterministic: read the PDF with pypdf, page by page, into a text blob. No judgment needed. |
| `inspect-data` | `execution` | Deterministic: enumerate sheets and produce shape/dtype/head. Gives the client a compact grounding without loading the whole workbook into state. |
| `answer-question` | `client_task` | Requires judgment: match question phrasing to background rules, choose sheet/columns, write and run analysis code. Different questions need different Python. Cannot be a script because the logic changes per question; cannot be a decision because the answer space is unbounded (any number). |
| `write-answer` | `execution` | Deterministic: validate `^-?\d+(\.\d+)?$` and write to `answer_path`. Keeping this out of the client task guarantees answers never bypass the format check. |
| `end` | `end` | Declares the final state's keys (`answer_written`, `answer_path`). |

No `decision` or `router` steps: the pipeline is linear and every question flows through the same shape.

Scripts (`extract_background.py`, `inspect_data.py`, `write_answer.py`) are kept lean and use only libraries present in the container. They speak the AIP execution contract: JSON on stdin containing `currentState`, one JSON object on stdout to merge.

## Deliberate drops (from the source skills, not carried into the compiled skill)

None of the following are actionable for this task; each is intentionally not represented in the body or scripts.

### From `xlsx/SKILL.md`

- **Financial model color-coding standards** (blue for inputs, black for formulas, green for cross-sheet links, red for external, yellow highlights). The task only reads a workbook; no cells are written.
- **Number formatting standards** (currency `$#,##0`, percentages `0.0%`, multiples `0.0x`, parenthesized negatives, "-" for zeros, year-as-text). Same reason — no writing.
- **Formula construction rules** (assumptions in separate cells, cell references over hardcodes, documentation-source comments). Same reason.
- **"Use Excel formulas, not hardcoded values" section** with the wrong/right code examples. The task's answer is a number, not a re-authored workbook.
- **Creating new Excel files** (openpyxl `Workbook`, `Font`, `PatternFill`, `Alignment`, column widths). Not needed.
- **Editing existing Excel files** — the insert-rows / delete-cols / add-sheet workflow. The task never mutates the source.
- **Recalculating formulas with `recalc.py`** and the LibreOffice bootstrap. LibreOffice is not in the task container, and the data workbook is analyzed for values only.
- **Formula verification checklist** (test 2–3 references, column mapping, `#REF!`/`#DIV/0!`/`#VALUE!`/`#NAME?` diagnosis). Same — no formulas being authored.
- **Zero-formula-errors, preserve-existing-templates output requirements**. Same.
- **Library-selection best practices** (pandas vs openpyxl for output). Reduced to a one-line default in `references/pandas-openpyxl-patterns.md`.
- **Code-style guidance** (concise Python, cell-comment sources). Not load-bearing for the answer.

### From `pdf/SKILL.md` and `pdf/references/*`

- **All form-filling content**: `forms.md`, `check_fillable_fields.py`, `extract_form_field_info.py`, `fill_fillable_fields.py`, `fill_pdf_form_with_annotations.py`, `check_bounding_boxes.py`, `check_bounding_boxes_test.py`, `create_validation_image.py`, `convert_pdf_to_images.py`. The background PDF is a static document; no form is filled.
- **pypdf merge / split / rotate / encrypt / decrypt** examples. Not needed.
- **pdfplumber**, **reportlab**, **pypdfium2**, **pdf-lib**, **pdfjs-dist**, **poppler-utils**, **qpdf**, **pdftk**, **pdftoppm**, **pdfimages**, **pdftotext**, **pytesseract**, **pdf2image** — none of these libraries or command-line tools are present in the container. Recipes for them are dropped rather than carried as false-promise instructions.
- **OCR for scanned PDFs** — background PDFs in this task are text PDFs; pytesseract and pdf2image are not installed.
- **Watermarking, image extraction, cropping, batch processing, encryption/decryption, page rotation, PDF repair** — none serve the task shape.
- **Advanced table extraction with pdfplumber `table_settings`** — pdfplumber is not installed. If a future task needs it, this drop must be revisited.
- **Metadata extraction with `PdfReader.metadata`** — not needed to answer the question; the useful signal is the body text.
- **License information section** listing library licenses — not actionable.

Rules, thresholds, lookups, branching, and the context needed to apply them are all preserved. Everything dropped above is either output-authoring (this task only reads) or belongs to a library the frozen container does not ship.

## Where the surviving knowledge went

- **pypdf text extraction** → `scripts/extract_background.py` (execution) and `references/pypdf-patterns.md` (on-demand load when the extracted text is ambiguous).
- **pandas raw-load-and-coerce, openpyxl `data_only=True`, header-row pitfalls, Excel/pandas 1-vs-0 indexing** → `references/pandas-openpyxl-patterns.md`, plus inlined defaults in `assets/analysis_template.md`.
- **The overall "read-PDF-first, then interpret-XLSX, then compute, then write" order** → the AIP graph itself, plus the step-by-step method in `assets/analysis_template.md`.
