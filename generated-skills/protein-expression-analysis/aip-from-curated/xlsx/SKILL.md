---
name: xlsx
description: "Comprehensive spreadsheet creation, editing, and analysis with support for formulas, formatting, data analysis, and visualization. When Claude needs to work with spreadsheets (.xlsx, .xlsm, .csv, .tsv, etc) for: (1) Creating new spreadsheets with formulas and formatting, (2) Reading or analyzing data, (3) Modify existing spreadsheets while preserving formulas, (4) Data analysis and visualization in spreadsheets, or (5) Recalculating formulas"
license: Proprietary. LICENSE.txt has complete terms
compatibility: Requires Python with pandas and openpyxl installed, plus LibreOffice (soffice) on PATH for formula recalculation. Linux or macOS.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Create, edit, and analyze spreadsheet files (.xlsx, .xlsm, .csv, .tsv) with full support for
  formulas, formatting, multi-sheet workbooks, and data analysis. Every delivered workbook
  must have zero formula errors. Any workbook containing formulas must be recalculated via
  LibreOffice before delivery — openpyxl writes formulas as strings without computed values.
  When modifying an existing file, preserve its established formatting and conventions. When
  authoring a financial model from scratch, follow the industry-standard color, number, and
  formula conventions in references/financial-model-standards.md.

trigger_when:
  - User asks to create, edit, or analyze a spreadsheet file (.xlsx, .xlsm, .csv, .tsv).
  - Creating new spreadsheets with formulas and formatting.
  - Reading or analyzing data from a spreadsheet.
  - Modifying an existing spreadsheet while preserving formulas and formatting.
  - Performing data analysis or visualization where the result lives in a spreadsheet.
  - Recalculating formula values after openpyxl writes.
  - Building a financial model, valuation, projection, or scenario workbook.

do_not_use_when:
  - The task is plain CSV row manipulation with no formulas, formatting, or Excel-specific features — standard text/CSV tooling is simpler.
  - The target is Google Sheets via API — this skill targets local files via pandas / openpyxl / LibreOffice.

scope_and_approval: >
  This skill writes to and overwrites local spreadsheet files. When editing an existing
  workbook with unknown contents, read it before modifying so existing conventions are
  preserved. Recalculation runs LibreOffice headlessly on the local machine and may take
  up to ~30 seconds per file. No network actions required.

steps:
  - name: classify-task
    description: >
      Identify the task type (create new / edit existing / analyze only) and pick the
      library. pandas — data analysis, bulk reads/writes, statistics, pivots, simple
      exports. openpyxl — formulas, cell styles, fonts, fills, comments, multiple sheets.
      The two can be combined in one workflow. See references/pandas-patterns.md and
      references/openpyxl-patterns.md.
    outputs:
      - name: task-type
        type: string
        description: one of "create", "edit", or "analyze"
      - name: library-choice
        type: string
        description: pandas, openpyxl, or both

  - name: study-existing-template
    description: >
      Only run when task-type is "edit". Load the workbook with openpyxl (without
      data_only=True) and record its column headers, number formats, fill colors, font
      colors, and formula patterns. Existing template conventions override the
      financial-model defaults in references/financial-model-standards.md — never impose
      standardized formatting on a file that already has its own established patterns.
    depends_on: [classify-task]
    inputs:
      - name: task-type
        type: string
    outputs:
      - name: template-conventions
        type: object
        nullable: true
        description: observed formatting, color, and formula conventions to preserve

  - name: load-or-create-workbook
    description: >
      Create a new workbook with openpyxl.Workbook(), or load an existing one with
      load_workbook(path). For workbooks that contain formulas, NEVER pass data_only=True
      and then save — that silently replaces every formula with its last cached value.
      For pure analysis, prefer pandas.read_excel. Patterns in
      references/openpyxl-patterns.md and references/pandas-patterns.md.
    depends_on: [classify-task]
    inputs:
      - name: task-type
        type: string
      - name: library-choice
        type: string
    outputs:
      - name: workbook
        type: object

  - name: write-data-and-formulas
    description: >
      Add or modify data, formulas, and formatting. Use Excel formulas for every total,
      growth rate, average, ratio, percentage, and difference — never compute the value
      in Python and write a hardcoded number, that breaks downstream updates. Place every
      assumption (growth rate, margin, multiple) in its own cell and reference it with
      $-anchored cell refs, e.g. =B5*(1+$B$6) not =B5*1.05. For new financial models,
      apply the color, number, and formula conventions in
      references/financial-model-standards.md; when template-conventions is non-null,
      those override the defaults. Code style guidance for the Python and the cells lives
      in references/code-style.md.
    depends_on: [load-or-create-workbook]
    inputs:
      - name: workbook
        type: object
      - name: template-conventions
        type: object
        nullable: true
    outputs:
      - name: modified-workbook
        type: object
      - name: has-formulas
        type: boolean

  - name: save-workbook
    description: >
      Persist the workbook with wb.save(path). openpyxl writes formulas as strings;
      computed values stay blank until recalculation.
    depends_on: [write-data-and-formulas]
    inputs:
      - name: modified-workbook
        type: object
    outputs:
      - name: saved-path
        type: string

  - name: recalculate-formulas
    description: >
      Mandatory whenever has-formulas is true. Drives LibreOffice headless to recalculate
      every formula in every sheet and scan all cells for Excel errors. Returns JSON with
      status, total_errors, total_formulas, and per-error-type locations. Skip this step
      only when the workbook contains no formulas.
    script: scripts/recalc.py
    depends_on: [save-workbook]
    inputs:
      - name: saved-path
        type: string
      - name: has-formulas
        type: boolean
    outputs:
      - name: recalc-report
        type: object
        description: JSON from recalc.py — status, total_errors, total_formulas, error_summary

  - name: fix-formula-errors
    description: >
      Only when recalc-report.status is "errors_found". Read error_summary and walk every
      reported location for #REF!, #DIV/0!, #VALUE!, #NAME?, #NULL!, #NUM!, and #N/A.
      Correct the underlying issue (bad reference, missing IFERROR guard, wrong function
      name, wrong data type), re-save, then re-run recalculate-formulas. Loop until
      status is "success". Error-by-error interpretation in
      references/verification-checklist.md.
    depends_on: [recalculate-formulas]
    inputs:
      - name: recalc-report
        type: object
    outputs:
      - name: clean-workbook-path
        type: string

  - name: verify-output
    description: >
      Final delivery gate. Confirm zero formula errors, that every formula cell shows a
      computed value, that hardcoded values have a source comment or adjacent note in the
      documented format, and that color and number formatting match either the existing
      template conventions or the financial-model defaults. Run the checklist in
      references/verification-checklist.md.
    depends_on: [fix-formula-errors]
    inputs:
      - name: clean-workbook-path
        type: string
    outputs:
      - name: delivery-ready
        type: boolean

search_shortcuts:
  - category: Libraries
    body: >
      pandas — data analysis, bulk reads/writes, statistics, group-by, pivot, simple
      exports. openpyxl — formulas, cell styles, fonts, fills, comments, multiple sheets,
      column widths, cell-level number formats. LibreOffice (soffice) — headless formula
      recalculation, driven by scripts/recalc.py.
  - category: Reference docs
    body: >
      references/financial-model-standards.md — color and number formatting conventions,
      formula construction rules, source-citation format for hardcoded values.
      references/openpyxl-patterns.md — workbook lifecycle, formulas, formatting,
      multi-sheet handling, data_only pitfalls. references/pandas-patterns.md —
      read_excel / to_excel, dtype / parse_dates / usecols, NaN handling.
      references/verification-checklist.md — pre-build sanity checks and recalc.py error
      interpretation. references/code-style.md — Python and in-workbook commenting style.

anti_patterns:
  - Computing totals, growth rates, averages, or ratios in Python and writing the result as a hardcoded number instead of an Excel formula. The spreadsheet must stay dynamic.
  - Loading an existing workbook with data_only=True and then saving it. That silently destroys every formula.
  - Imposing the default financial-model color and number formatting on a file that already has its own established conventions. Existing template wins.
  - Skipping recalc.py after writing formulas with openpyxl. Formula cells stay blank without it, and errors are invisible.
  - Delivering a workbook with any #REF!, #DIV/0!, #VALUE!, #N/A, #NAME?, #NULL!, or #NUM! errors.
  - Embedding assumption numbers (growth rates, margins, multiples) directly in formulas instead of referencing a dedicated assumption cell anchored with $.
  - Hardcoding source-data values with no "Source - [System], [Date], [Reference]" comment or adjacent note.
  - Mistaking column-index numbers — Excel column 64 is BL, not BK. DataFrame row 5 is Excel row 6 (1-indexed).
```
