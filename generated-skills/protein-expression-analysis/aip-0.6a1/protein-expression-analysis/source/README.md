# Source and provenance — protein-expression-analysis

## Provenance

| File | Origin | Use |
|---|---|---|
| `xlsx/SKILL.md` | curated input skill `xlsx` (Anthropic, proprietary; `xlsx/LICENSE.txt`) | Spreadsheet rules: formulas not hardcodes, zero formula errors, preserve templates, LibreOffice recalculation, verification checklist |
| `xlsx/recalc.py` | same skill | Adapted into `scripts/recalc.py` (see below) |
| `xlsx/LICENSE.txt` | same skill | Licence terms, referenced from frontmatter `license` |

All three are copied verbatim. Task context (not copied, read at authoring time): the
task statement (Task sheet C11:L20 lookups, B24:K27 transposed group statistics,
C32:D41 fold changes, log2 data, Control/Treated in row 9, prefixed sample names, no
macros, formulas only, keep formatting), the real `protein_expression.xlsx` (Task + Data,
200 proteins x 50 samples, 17 blank cells among the 100 looked-up values), and the
container Dockerfile (Ubuntu 24.04, python3 3.12, openpyxl 3.1.5, LibreOffice, gnumeric;
**no pandas**).

## Intent

One autonomous pass that fills the workbook with live formulas, recalculates it so
cached values exist, and proves every value against an independent computation, while
leaving every style untouched. It must work for other instances of the task (different
proteins, samples, group order, prefixed names, values) without fixed addresses.

## Graph and step-kind choices

| Step | Kind | Why |
|---|---|---|
| `inspect-layout` | execution | Locating blocks, resolving names, profiling blanks and checking yellow-cell coverage is deterministic over the file. Emits explicit target-cell lists so nothing downstream hardcodes addresses. |
| `judge-task` | decision | Two judgments with a fixed answer space: blank-cell policy (`exclude`/`zero`, depends on what the task statement says) and whether the detected layout matches the statement (noul). Thresholds flag close calls. |
| `confirm-layout` | client_task | Corrections, when needed, are free-form cell lists only the agent can produce; usually an empty object. A router could not be used here because the fill step must read one `layout_overrides` key on every path. |
| `fill-workbook` | execution | Formula generation, save, LibreOffice recalc, independent Python verification, style diff: all deterministic. |
| `route-verdict` | router | `verified` ends; `needs_attention` goes to repair. |
| `resolve-issues` | client_task | Repairs depend on the specific failure (recalc crash, absent protein, style drift) and need agent judgment, guided by the reference checklist. |

Script notes: three files only. `inspect_layout.py` and `fill_workbook.py` are independent
steps; `recalc.py` is the source script with these adaptations: `subprocess(timeout=)`
instead of the external `timeout`/`gtimeout` binary (portable, and `requires` then only
needs `soffice`), a 90 s non-raising first-run profile init (the original 10 s
`TimeoutExpired` could crash on a cold container), `soffice` looked up on PATH, and the
default timeout raised to 120 s. Its macro, error list and JSON report are unchanged.
Backups (original and formulas-only copy) go to a `tempfile` directory, not next to the
deliverable.

Design decision on blanks: a bare INDEX/MATCH returns 0 for an empty Data cell, which on
a log2 scale is a real value. The default `exclude` keeps blanks blank (`IF(x="","",x)`),
uses COUNT guards so a group with no values gets a blank mean and fewer than 2 values a
blank stdev, and keeps the sheet error-free (the source's zero-error rule). `zero` exists
only for a task statement that explicitly asks for it.

## Completeness walk (source → skill)

`xlsx/SKILL.md`, in order:

| Source item | Where it lives |
|---|---|
| Zero formula errors (#REF!, #DIV/0!, #VALUE!, #N/A, #NAME?) | `fill_workbook.py` (recalc error scan → needs_attention), COUNT guards, `resolve-issues` template, guide repair checklist |
| Preserve existing templates; template conventions override | style snapshot diff in `fill_workbook.py`; anti-pattern on restyling; guide gotchas |
| LibreOffice required; recalc.py configures itself | `scripts/recalc.py`, `requires.tools: soffice` |
| Use formulas, not hardcoded values (WRONG/CORRECT examples) | every target written as a formula; anti-patterns 1 and 6; confirm-layout template forbids numbers in overrides |
| Common workflow 1–6 (choose tool, load, modify, save, recalc mandatory, verify and fix by error type) | `fill-workbook` (openpyxl load → formulas → save → recalc → verify) and `resolve-issues` (fix by error type) |
| Editing existing files with openpyxl | `fill_workbook.py` |
| Recalculating formulas; script output JSON (status, total_errors, error_summary, total_formulas) | `scripts/recalc.py`; surfaced as `fill_report.recalc` |
| Verification: test sample references | every target value checked against an independent Python computation |
| Column mapping / row offset | openpyxl `get_column_letter` / 1-based rows throughout; far-right Data columns found by scanning the header (`last_col`) |
| NaN handling | `missing_value_policy` decision + blank-preserving formulas |
| Multiple matches | duplicate Data ID / header warnings in `inspect_layout.py` |
| Division by zero | COUNT guards on AVERAGE / STDEV |
| Wrong references / cross-sheet reference format | independent verification; sheet names quoted when needed (`qs()`) |
| Verify dependencies / edge cases (zero, negative, large) | blanks and sparse groups handled; negative log2 values exercised by the real data |
| openpyxl 1-based cells; `data_only=True` save destroys formulas | anti-pattern; guide gotchas |
| Formulas preserved but not evaluated → use recalc | anti-pattern "delivering formulas without recalculating"; fill step always recalcs |

Task statement items: lookup on protein ID + sample name (INDEX/MATCH) → fill step;
groups from row 9 → `groups` detection; mean/stdev per group on log2 data → stats
formulas; Log2 FC = Treated − Control, FC = 2^Log2 FC → fold-change formulas and
anti-pattern; yellow cells B24:K27 / C32:D41 → explicit cell lists, yellow coverage
check; no macros/VBA, keep format/colours/fonts → anti-patterns + style diff; prefixed
sample names → `contains` resolution with wildcard MATCH.

## Deliberate drops

| Dropped | Rationale |
|---|---|
| Financial-model colour coding (blue inputs, black formulas, green cross-sheet links, …) | Not a financial model; the task forbids changing colours/fonts and the source itself says template conventions override these guidelines. |
| Number-format standards (years, currency, %, multiples, parentheses for negatives) | Financial-model only; target cells keep the template's existing General format. |
| Assumptions placement in separate cells | No assumptions exist; the only constants (2 as the log base) are intrinsic to the formula. |
| Documenting hardcodes with source comments; adding cell comments to complex formulas | No hardcoded values are written; adding comments would alter the delivered file, which the task forbids. |
| pandas reading/writing examples and pandas tips (dtype, usecols, parse_dates) | pandas is not installed in the container; openpyxl covers all reads. |
| Creating new workbooks; insert_rows / delete_cols / create_sheet examples | The task edits an existing template in place; restructuring would break the layout. |
| read_only / write_only modes for large files | The workbook is ~120 KB. |
| "Start small: test formulas on 2–3 cells first" | Superseded by automatic verification of every target cell after recalculation. |
| Code style guidelines for generated Python (minimal, few comments, no prints) | Guidance for writing ad-hoc code; the skill ships finished scripts whose stdout must be exactly one JSON object. |
| macOS `gtimeout` handling in recalc.py | Replaced by subprocess timeouts (same behaviour, no extra binary). |
| Overview / library-selection prose | Background; the chosen library is fixed by the container. |

## Functional test record

Run locally with `aip run` / `aip resume` against the real file and two generated
instances (different proteins, interleaved Control/Treated columns, short sample names
needing prefix matching, perturbed values; one with a protein absent from Data).
LibreOffice is not installed on the authoring machine, so a test-only `soffice` stand-in
(in the scratch area, not shipped) evaluated the workbook with the independent
`formulas` library and injected cached values. Real file → `verified` (160 formulas,
0 errors, all 160 values match, styles identical). Variant → `verified`. Variant with
absent protein → `needs_attention` → `resolve-issues` (IFERROR wrap for that row,
re-recalc, 0 errors). Also checked: `zero` policy verifies; a LibreOffice crash yields
`needs_attention`; a machine without `soffice` stops at the `requires` check.
