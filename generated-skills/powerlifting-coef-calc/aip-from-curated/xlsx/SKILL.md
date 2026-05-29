---
name: xlsx
description: "Comprehensive spreadsheet creation, editing, and analysis with support for formulas, formatting, data analysis, and visualization. When Claude needs to work with spreadsheets (.xlsx, .xlsm, .csv, .tsv, etc) for: (1) Creating new spreadsheets with formulas and formatting, (2) Reading or analyzing data, (3) Modify existing spreadsheets while preserving formulas, (4) Data analysis and visualization in spreadsheets, or (5) Recalculating formulas"
license: Proprietary. LICENSE.txt has complete terms
compatibility: Requires LibreOffice (soffice on PATH), Python 3, openpyxl, and pandas. recalc.py auto-configures the LibreOffice macro on first run; works on Linux and macOS.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Create, edit, and analyze spreadsheet files (.xlsx, .xlsm, .csv, .tsv) end-to-end.
  Covers library choice (pandas for data, openpyxl for formulas/formatting), formula
  authoring that stays dynamic (no Python-computed hardcodes), LibreOffice-backed
  recalculation, and an error-driven verification loop. Output contract: every Excel
  model is delivered with ZERO formula errors (#REF!, #DIV/0!, #VALUE!, #N/A, #NAME?,
  #NULL!, #NUM!) and, when editing an existing file, preserves the file's existing
  template, style, and conventions exactly.

trigger_when:
  - User asks to create a new .xlsx, .xlsm, .csv, or .tsv file.
  - User asks to read, analyze, summarize, or visualize data in a spreadsheet.
  - User asks to modify an existing spreadsheet while preserving formulas/formatting.
  - User asks for a financial model, projection, or any workbook driven by formulas.
  - User asks to recalculate formulas, fix formula errors, or audit a workbook.

do_not_use_when:
  - Task is a pure CSV/TSV read with no need for formulas, formatting, or multi-sheet
    workbooks — plain pandas without this skill is sufficient.
  - Task is a one-off tabular print to terminal that will not be saved as a workbook.

scope_and_approval: >
  Zero formula errors is a hard contract on every delivered workbook. When editing an
  existing file, the file's established formatting, color scheme, naming, and structure
  ALWAYS override the conventions in references/financial-models.md — never impose
  standardized formatting on a workbook with its own established patterns. Use Excel
  formulas, not Python-computed values, for ALL calculations (totals, percentages,
  ratios, differences) so the workbook remains dynamic. Loading an existing workbook
  with openpyxl's `data_only=True` and then saving will permanently replace formulas
  with values — never do this on a file the user wants to keep editable.

steps:
  - name: classify-task
    description: >
      Decide which workflow applies — (a) create new, (b) edit existing, (c) read/analyze.
      For (b), open the file first and study its existing format, style, naming, and
      conventions; those override anything in references/financial-models.md. For any
      financial-model output without an existing template, load references/financial-models.md
      for color coding, number formatting, and formula construction conventions.
    outputs:
      - name: workflow-kind
        type: string
        description: "One of: create | edit | analyze"
      - name: template-conventions
        type: object
        nullable: true
        description: For edit tasks, the observed conventions to preserve.

  - name: choose-library
    description: >
      Use pandas for data analysis, bulk operations, and simple data export. Use openpyxl
      for formulas, formatting, multi-sheet structure, cell comments, or anything that
      must be preserved on round-trip. If the task needs BOTH (e.g., analyze with pandas,
      then write a formula-bearing output), use each library for what it is good at.
      See references/openpyxl-patterns.md for create/edit snippets and library tips.
    depends_on: [classify-task]
    inputs:
      - name: workflow-kind
        type: string
    outputs:
      - name: library-choice
        type: string
        description: "pandas | openpyxl | both"

  - name: load-or-create
    description: >
      For create — instantiate a new Workbook (openpyxl) or build a DataFrame (pandas).
      For edit — load with openpyxl (`load_workbook(path)`); never use `data_only=True`
      on a file you intend to save back, or formulas will be replaced with values and
      permanently lost. For analyze — read with pandas (`pd.read_excel`); pass
      `sheet_name=None` if multiple sheets are relevant.
    depends_on: [choose-library]
    inputs:
      - name: library-choice
        type: string
    outputs:
      - name: workbook
        type: object
        description: openpyxl Workbook handle or pandas DataFrame(s).

  - name: modify
    description: >
      Add, edit, or restructure cells, sheets, and formatting. Use Excel formulas
      (`=SUM(...)`, `=AVERAGE(...)`, `=(C4-C2)/C2`, etc.) for ALL calculations —
      never compute the value in Python and hardcode the result. Place assumptions
      in separate cells and reference them, e.g. `=B5*(1+$B$6)` not `=B5*1.05`.
      Use 1-based cell indices. For cross-sheet references, use `Sheet1!A1` form.
      Guard division denominators (wrap in `IFERROR` or `IF(denom=0, ...)`) to avoid
      `#DIV/0!`. For financial models without an existing template, follow the
      conventions in references/financial-models.md.
    depends_on: [load-or-create]
    inputs:
      - name: workbook
        type: object
      - name: template-conventions
        type: object
        nullable: true
    outputs:
      - name: modified-workbook
        type: object

  - name: save
    description: >
      Save the workbook to disk (`wb.save('path.xlsx')` or `df.to_excel('path.xlsx',
      index=False)`). Use the path the user named; do not silently rename or relocate.
    depends_on: [modify]
    inputs:
      - name: modified-workbook
        type: object
    outputs:
      - name: file-path
        type: string

  - name: recalc-formulas
    description: >
      MANDATORY whenever the workbook contains any Excel formula authored or modified
      in this run. openpyxl writes formulas as strings but does not compute their values.
      Runs `python scripts/recalc.py <file> [timeout_seconds]` which drives a headless
      LibreOffice to evaluate every formula and scans all cells for Excel errors.
      Returns JSON with `status`, `total_errors`, `total_formulas`, and (if errors)
      `error_summary` per error type with cell locations.
    script: scripts/recalc.py
    depends_on: [save]
    inputs:
      - name: file-path
        type: string
    outputs:
      - name: recalc-report
        type: object

  - name: verify-and-fix
    description: >
      Inspect `recalc-report`. If `status` is `success` and `total_errors` is 0, the
      workbook meets the zero-error contract — done. If `status` is `errors_found`,
      walk `error_summary` and fix every listed cell (see references/formula-verification.md
      for the meaning of each error type and the verification checklist). Return to
      `modify` (or earlier if the root cause is structural), then `save`, then re-run
      `recalc-formulas`. Loop until `total_errors` is 0.
    depends_on: [recalc-formulas]
    inputs:
      - name: recalc-report
        type: object
    outputs:
      - name: verified-file-path
        type: string
        description: Path to a workbook that passed recalc with zero errors.

scenarios:
  - need: >
      Compute a new column in an existing workbook that combines existing columns.
    context: >
      User has an `.xlsx` with raw data in one sheet and an empty sheet for outputs;
      asks for a derived column computed from existing columns at fixed precision.
    action: >
      Load the workbook with openpyxl (NOT data_only=True). Copy the required source
      columns into the target sheet preserving column order and names. Append the new
      column header. Write an Excel formula per row that references the source cells
      (NOT a Python-computed value). Save. Run scripts/recalc.py. If errors_found,
      fix flagged cells and re-run.
    outcome: >
      A dynamic workbook where the new column recomputes automatically if source data
      changes, with zero formula errors on recalc.

  - need: >
      Build a financial projection from scratch with assumptions and growth rates.
    context: No existing template — conventions in references/financial-models.md apply.
    action: >
      Create a Workbook. Place assumptions in their own cells (blue text). Reference
      them from formulas (black text). Format currency as `$#,##0`, percentages as
      `0.0%`, zeros as `-`. Save, run scripts/recalc.py, fix any errors, re-run.
    outcome: A model that recomputes scenarios by editing the assumption cells alone.

  - need: User asks "what's in this workbook?" with no edits requested.
    context: Read-only analysis task.
    action: >
      Use pandas (`pd.read_excel('file.xlsx', sheet_name=None)`) to load all sheets.
      Report shape, columns, dtypes, summary stats. Do not save unless the user asks.
    outcome: Summary delivered; original file untouched.

anti_patterns:
  - >-
    Computing a total / growth rate / average in Python and writing the literal value
    into a cell (e.g., `sheet['B10'] = df['Sales'].sum()`). Use `=SUM(B2:B9)` instead.
  - >-
    Imposing standardized financial-model formatting on an existing workbook that
    already has its own conventions.
  - >-
    Opening an existing file with `load_workbook(path, data_only=True)` and then
    saving — this permanently replaces every formula with its computed value.
  - >-
    Skipping `scripts/recalc.py` after writing formulas. openpyxl does not evaluate
    them; without recalc the file ships with stale or missing computed values.
  - >-
    Hardcoding values without documenting their source. For finance work, comment
    the cell with a Source line — System/Document, Date, Reference, URL.
  - >-
    Declaring the task complete on `recalc.py` errors_found without fixing them.
  - >-
    Forgetting Excel rows are 1-indexed (DataFrame row 5 → Excel row 6) or that
    column 64 is `BL` (not `BK`), producing off-by-one references.
```
