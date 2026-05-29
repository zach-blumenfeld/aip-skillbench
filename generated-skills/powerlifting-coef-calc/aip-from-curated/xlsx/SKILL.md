---
name: xlsx
description: "Create, edit, analyze, and recalculate Excel workbooks (.xlsx, .xlsm, .csv, .tsv) with formula correctness as a hard requirement — formulas (never hardcoded Python values) for all derived cells, verified zero formula errors via LibreOffice recalc, and financial-model conventions (color coding, number formats, assumption placement) when applicable. Use when (1) creating new spreadsheets with formulas and formatting, (2) reading or analyzing tabular data, (3) modifying existing workbooks while preserving formulas, (4) building data analyses or visualizations in Excel, (5) recalculating formulas written by openpyxl, (6) shipping a workbook free of #REF!/#DIV/0!/#VALUE!/#N/A/#NAME? errors, or whenever the user mentions xlsx, Excel, openpyxl, pandas+Excel, financial models, or formula recalc."
license: Proprietary. LICENSE.txt has complete terms
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3 with pandas and openpyxl. LibreOffice (soffice) must be installed on PATH — scripts/recalc.py drives it headlessly and configures the macro on first run. Works on Linux and macOS.
---

```yaml
purpose: >
  Drive Excel workbook lifecycle end to end with formula correctness as a
  hard ship requirement. The flow is: pick the right library (pandas for
  bulk data, openpyxl for formulas and formatting), load or create the
  workbook, write derived values as Excel formula strings (never as
  Python-computed numbers), apply formatting (matching an existing
  template's style when present, otherwise the financial-model
  conventions in scripts/financial_format.py when relevant), save,
  recalculate every formula via scripts/recalc.py (which drives headless
  LibreOffice and reports errors as JSON), then iterate until zero
  formula errors remain. The bundled recalc helper is mandatory whenever
  the workbook contains formulas — openpyxl writes formulas as strings
  with no computed value, so the file is unevaluated until the recalc
  step runs.

trigger_when:
  - Creating a new .xlsx / .xlsm workbook that will contain formulas or formatting.
  - Editing an existing workbook while preserving its formulas, styles, and structure.
  - Reading or analyzing tabular data out of Excel files.
  - Recalculating a workbook that openpyxl wrote (formula cells are unevaluated until recalc runs).
  - Building or extending a financial model (DCF, projections, scenario analysis, comp tables).
  - Verifying that a workbook ships with zero formula errors (#REF!, #DIV/0!, #VALUE!, #N/A, #NAME?, #NUM!, #NULL!).
  - User mentions xlsx, xlsm, Excel, openpyxl, pandas read_excel / to_excel, formulas, recalculation, or financial-model formatting.

do_not_use_when:
  - The target is not Excel — Google Sheets API, native LibreOffice .ods, or other formats live in different toolchains.
  - The task is a pure CSV transformation with no formulas, no styles, and no sheets — pandas alone is sufficient; the recalc step is wasted overhead.

scope_and_approval: >
  Writes files at the paths the agent or user specifies. The recalc step
  spawns a headless LibreOffice process and overwrites the workbook in
  place with computed values. Confirm before overwriting any file the
  user did not explicitly target; in-session scratch files are fine
  without prompting. Read-only operations (pd.read_excel,
  load_workbook + inspect) need no approval.

steps:
  - name: choose-library
    description: >
      Pick by the operation, not the file extension. pandas for bulk
      tabular analysis, statistics, or simple value-only export.
      openpyxl for anything touching formula strings, cell styles,
      number formats, sheet structure, comments, or merged cells. When a
      task needs both (read tabular data → write formulas), do the read
      with pandas and the write with openpyxl on the same file. pandas
      writes literal values only — it will never produce a live formula
      cell.
    inputs:
      - name: operation-kind
        type: string
        description: 'One of "analyze", "create-with-formulas", "edit-preserving-formulas", "bulk-export".'
    outputs:
      - name: library-choice
        type: string
        description: '"pandas" or "openpyxl" (or both, for read-pandas/write-openpyxl flows).'

  - name: load-or-create-workbook
    description: >
      For a new file use openpyxl `Workbook()`. For edits use
      `load_workbook(path)` — NEVER `load_workbook(path, data_only=True)`
      if you intend to save back; that mode replaces formula cells with
      their cached values and writing the workbook destroys every
      formula irrecoverably. Use `data_only=True` only for read-only
      value snapshots. For large reads, pass `read_only=True` (openpyxl)
      or `usecols=`/`dtype=`/`parse_dates=` (pandas) to keep memory and
      type inference in check. Cell indices are 1-based — column 64 is
      BL, not BK, and DataFrame row 5 maps to Excel row 6.
    depends_on: [choose-library]
    inputs:
      - name: path
        type: string
      - name: mode
        type: string
        description: '"create" | "edit" | "read" | "read-snapshot".'
    outputs:
      - name: workbook
        type: object

  - name: write-formulas-not-values
    description: >
      Every derived cell — totals, ratios, growth rates, averages,
      differences, lookups — MUST be written as an Excel formula string
      (`=SUM(B2:B9)`, `=(C4-C2)/C2`, `=AVERAGE(D2:D19)`), never as a
      Python-computed number assigned to a cell. The workbook must
      remain re-evaluable when source data changes. Place ALL assumption
      inputs (growth rates, margins, multiples, coefficients) in
      dedicated cells and reference them (`=B5*(1+$B$6)` rather than
      `=B5*1.05`) so scenario edits are a one-cell change. Test 2–3
      sample formulas before broadcasting a pattern across hundreds of
      cells — off-by-one ranges and wrong column letters compound.
    depends_on: [load-or-create-workbook]
    inputs:
      - name: workbook
        type: object
      - name: assumption-cells
        type: object
        description: Map of cell coordinate → starting value for inputs the user may edit.
      - name: derived-cells
        type: object
        description: Map of cell coordinate → Excel formula string.

  - name: apply-formatting
    description: >
      Two branches. (a) Editing an existing workbook with established
      style — inspect the existing fonts, colors, number formats, and
      column widths BEFORE writing, then match them. Existing template
      conventions override every default in this skill. (b) New
      financial-model sheet with no incumbent style — import
      `scripts/financial_format.py` and call `apply_role(cell, role,
      number_format=..., highlight=...)`. Roles: `input` (blue,
      hardcoded scenarios), `formula` (black, calculations),
      `cross_sheet` (green, links inside this workbook), `external`
      (red, links to other files). Number-format keys: `currency`,
      `currency_decimal`, `percent`, `multiple`, `year`, `integer`.
      Set `highlight=True` to add the yellow assumption-attention fill.
      Skip this step entirely for non-financial sheets where the user
      did not request the convention.
    script: scripts/financial_format.py
    depends_on: [write-formulas-not-values]
    inputs:
      - name: workbook
        type: object
      - name: cell-classifications
        type: object
        description: Per-cell role plus optional number_format key and highlight flag.
    outputs:
      - name: workbook
        type: object

  - name: save-workbook
    description: >
      `wb.save(path)` to persist. openpyxl writes formula CELLS as
      strings with no computed value — the next step recalculates them.
      For hardcoded inputs whose source must be traceable, attach an
      openpyxl `Comment` to the cell or write the citation
      ("Source: Company 10-K, FY2024, Page 45, [URL]") in the adjacent
      column.
    depends_on: [apply-formatting, write-formulas-not-values]
    inputs:
      - name: workbook
        type: object
      - name: path
        type: string
    outputs:
      - name: saved-path
        type: string

  - name: recalculate-formulas
    description: >
      Run `python scripts/recalc.py <path> [timeout_seconds]`. The
      script drives headless LibreOffice through a one-time Basic macro
      setup (created on first invocation), recalculates every formula
      in every sheet, scans every cell for Excel error sentinels, and
      prints a JSON report shaped
      `{status, total_formulas, total_errors, error_summary: {errType: {count, locations}}}`.
      MANDATORY whenever the workbook contains any formula. Skip ONLY
      for pure-value files with zero formulas.
    script: scripts/recalc.py
    depends_on: [save-workbook]
    inputs:
      - name: path
        type: string
      - name: timeout
        type: integer
        nullable: true
        description: Optional seconds before LibreOffice is killed; default 30.
    outputs:
      - name: recalc-report
        type: object
        description: '{status: "success"|"errors_found", total_formulas, total_errors, error_summary}.'

  - name: verify-and-fix-errors
    description: >
      Inspect `recalc-report`. If `status == "success"`, done. If
      `status == "errors_found"`, walk `error_summary` by error type and
      apply the right fix at each location, then re-save and re-run
      recalc. Loop until `total_errors == 0`. Error-type lookup —
      `#REF!`: a cell reference points nowhere (typo, off-by-one, or a
      deleted row/column); rebuild the reference. `#DIV/0!`: a
      denominator is zero; wrap in `IFERROR(num/denom, 0)` or guard
      with `IF(denom=0, 0, num/denom)`. `#VALUE!`: wrong data type in
      a formula argument (text where a number is expected); coerce or
      filter. `#NAME?`: unrecognized function name (typo, or a
      function LibreOffice cannot evaluate); replace with a supported
      equivalent. `#N/A`: a `VLOOKUP` / `MATCH` / `XLOOKUP` did not
      find the key; widen the range, fix the key, or wrap in
      `IFNA(..., default)`. `#NUM!`: numeric domain violation
      (negative under a sqrt, overflow). `#NULL!`: range syntax error
      (missing `:` or `,`). For each location reported in
      `error_summary[type].locations`, open the cell, identify which
      condition above applies, fix in place, and rerun.
    depends_on: [recalculate-formulas]
    inputs:
      - name: recalc-report
        type: object
      - name: workbook-path
        type: string
    outputs:
      - name: clean-workbook-path
        type: string
        description: Path to a workbook whose recalc-report has status == "success".

scenarios:
  - need: Build a five-year revenue projection with editable growth-rate assumptions.
    action: >
      openpyxl. Put starting revenue in B2 and growth rate in B3 — apply
      `input` role (blue) and `highlight=True` (yellow) so both are
      visibly editable. Project Year-1..Year-5 with
      `=B2*(1+$B$3)^n` formulas styled `formula` role (black). Save,
      then `python scripts/recalc.py model.xlsx`. Fix any errors and
      re-run until status is success.
    outcome: A workbook where editing B3 cascades to every projection year on next open.
  - need: Summarize sales data from an existing workbook into a new file with a live grand total.
    action: >
      Use pandas to `read_excel(src)` and groupby for the per-segment
      rollup. Switch to openpyxl for the write — pandas writes literal
      values only, so the grand total cell needs `=SUM(B2:B<last>)` as a
      formula string. Save, recalc, verify status is success.
    outcome: Summary file with a live total that updates when a category row is edited.
  - need: Extend an existing financial template that already uses bold red headers and a custom 0.00x number format.
    action: >
      `load_workbook(path)` (NOT `data_only=True`). Inspect the existing
      fonts, fills, and number_format strings on representative cells
      before writing. Match those — do NOT impose the
      financial_format.py palette. Existing template style overrides
      skill defaults.
    outcome: New rows that are visually indistinguishable from the template author's work.
  - need: Compute powerlifting coefficient × total for each lifter and rank the field.
    action: >
      Put the coefficient lookup table (e.g. Wilks or IPF GL constants)
      on a dedicated sheet, lifters and totals on the main sheet, and
      compute scores with `=VLOOKUP(..., Coefficients!A:B, 2, FALSE) *
      <total cell>` — never inline the coefficient as a Python float.
      Rank with `=RANK.EQ(...)`. Recalc, verify.
    outcome: Editing a coefficient on the lookup sheet re-ranks every lifter on next open.
  - need: recalc.py reports `#DIV/0!` at `Sheet1!G14` and `Sheet1!G15`.
    action: >
      Open each formula, identify the denominator (often a prior-period
      revenue that is 0 for a brand-new product), wrap with
      `=IFERROR(num/denom, 0)` or `=IF(denom=0, 0, num/denom)`. Save,
      re-run recalc, confirm status is success.
    outcome: Status flips to success with no remaining error categories.
  - need: A hardcoded constant needs a documentation trail (e.g. a quarterly revenue figure pulled from a 10-Q).
    action: >
      Put the number in its own cell with the `input` role (blue), then
      either attach an openpyxl `Comment` to the cell or write the
      citation in the adjacent column —
      "Source: Company 10-Q, Q2 2025, Exhibit 99.1, [SEC EDGAR URL]".
    outcome: Auditors can trace every blue cell back to its source without grepping the codebase.

anti_patterns:
  - Computing a total, growth rate, or average in Python and writing the *number* to a cell. The workbook stops being re-evaluable. Always write the formula string (`=SUM(...)`, `=AVERAGE(...)`, `=(C4-C2)/C2`) and let Excel evaluate.
  - Hardcoding constants inside formulas (`=B5*1.05`). Promote 1.05 to its own input cell and reference it (`=B5*(1+$B$6)`) so scenario edits are a single keystroke.
  - Opening with `load_workbook(path, data_only=True)` and then saving. The save replaces every formula with its cached value — the formulas are gone for good. Use `data_only=True` only when you intend to read a value snapshot and discard the workbook.
  - Skipping `scripts/recalc.py` because the formulas "look right". openpyxl writes formula text, not computed values. Until recalc runs, the file is unevaluated — any downstream consumer (pandas, BI tool, the user opening it in Excel) sees blank or stale cells.
  - Imposing the financial-model color palette on an existing template that already has its own conventions. The user's existing style wins; consistency inside the workbook beats consistency with the skill default.
  - Rolling out a formula pattern across hundreds of cells before testing 2–3 of them. Off-by-one ranges, wrong column letters (column 64 is BL, not BK), and 1-indexing surprises (DataFrame row 5 → Excel row 6) compound and cost a full rebuild.
  - Treating `#N/A` from a `VLOOKUP` / `XLOOKUP` as a formula bug. The formula is right; the lookup key is missing from the source range. Widen the range, fix the key, or wrap in `IFNA(..., default)`.
  - Leaving a hardcoded number blue without documenting its source. Future readers cannot tell whether $1.2B was a 10-K figure, an analyst estimate, or a guess. Attach a comment or cite the source in the adjacent column.
  - Using pandas `to_excel` and expecting a live grand-total row to appear as a formula. pandas writes literals — switch to openpyxl for any cell that needs to remain a formula.
  - Forgetting to re-run recalc after a fix. The fix is unevaluated until LibreOffice processes the file again; the next downstream read sees the broken-but-cached value.
```
