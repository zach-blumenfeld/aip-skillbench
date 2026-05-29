---
name: senior-data-scientist
description: Senior data scientist skill for statistical modeling, coefficient calculation, and spreadsheet-based analytical workflows. Encodes the OpenPowerlifting Dots coefficient formula (sex-specific quartic polynomial with bodyweight clamping) and the Excel-formula construction patterns needed to emit a "Dots" sheet that cross-references a raw "Data" sheet. Use when designing experiments, computing performance coefficients such as Dots, Wilks, or IPF Points, building formula-driven analysis sheets from OpenPowerlifting/OpenIPF workbooks, or any spreadsheet-workflow task that requires writing live Excel formulas (not precomputed values) at 3-digit precision.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.12+ and uv. Scripts pull polars, fastexcel, and xlsxwriter via PEP 723 inline metadata at run time.
---

```yaml
purpose: >
  Compute powerlifting performance scores — primarily the Dots coefficient — for
  OpenPowerlifting / OpenIPF competition data delivered as an Excel workbook with
  a populated "Data" sheet and an empty target sheet (typically "Dots"). The skill
  encodes the canonical Dots polynomial, sex-specific bodyweight clamps, the
  OpenPowerlifting column dictionary, and the xlsxwriter recipes needed to emit
  live Excel formulas (not precomputed Python values) at 3-digit precision while
  preserving the source column order and header names.

trigger_when:
  - User asks to compute Dots, Wilks, IPF Points, or any similar lifter coefficient on an OpenPowerlifting-style workbook.
  - The input is an .xlsx with a "Data" sheet of lifter records and an empty sibling sheet to fill in with coefficients.
  - Instruction calls for Excel *formulas* (rather than baked-in numeric values) for TotalKg and/or the coefficient column.
  - User references the OpenIPF / OpenPowerlifting schema (Best3SquatKg, Best3BenchKg, Best3DeadliftKg, BodyweightKg, Sex, etc.).
  - Spreadsheet-workflow task tagged powerlifting, sports analytics, or statistical scoring of tabular records.

do_not_use_when:
  - User explicitly asks for a different coefficient (Wilks, IPF GL Points, SBD-Score) without mentioning Dots — first confirm which formula they want; the Dots-specific polynomial constants in this skill do not apply.
  - The task is to *read* or analyze existing coefficient values rather than write the formulas — no specialized knowledge is required.
  - The workbook is not OpenPowerlifting-shaped (no Best3* / BodyweightKg / Sex columns); column selection in `select-dots-columns` will not map cleanly.

scope_and_approval: >
  The procedure writes a new .xlsx at the user-specified output path; it never
  edits the input workbook in place during computation. The reference solution
  flow `mv $OUTPUT_FILE $INPUT_FILE` is acceptable only when the task instruction
  explicitly requires updating the original file. Confirm with the user before
  overwriting any pre-existing file at the output path.

steps:
  - name: inspect-workbook
    description: Open the input workbook and capture sheet names, header row of the "Data" sheet, and total data-row count so column selection and formula targets are grounded in the actual headers rather than assumed ones.
    script: scripts/inspect_workbook.py
    inputs:
      - name: input-path
        type: string
        description: Absolute path to the input .xlsx file.
    outputs:
      - name: sheet-names
        type: list[string]
      - name: data-columns
        type: list[string]
        description: Header row of the Data sheet, in source order.
      - name: data-row-count
        type: integer

  - name: select-dots-columns
    description: >
      Resolve the Data-sheet columns required to compute Dots. The canonical
      selection — preserved in Data-sheet order, with header names unchanged —
      is Name, Sex, BodyweightKg, Best3SquatKg, Best3BenchKg, Best3DeadliftKg.
      The script returns each selected header alongside its 1-based source
      column index and its Excel column letter so downstream formulas can
      reference the correct Data!<col><row> cells. Column semantics are
      documented in references/openipf_data_columns.md.
    script: scripts/select_dots_columns.py
    inputs:
      - name: data-columns
        type: list[string]
    outputs:
      - name: selected-columns
        type: list[object]
        description: Each item carries `name`, `source_letter`, and target-sheet position.

  - name: build-dots-sheet
    description: >
      Write a new workbook containing the original "Data" sheet plus a populated
      "Dots" sheet. Dots columns A..F mirror the selected Data columns via
      cross-sheet references (e.g. `=Data!A2`); column G is TotalKg as a sum of
      the three best-lift columns; column H is the Dots coefficient as a
      sex-switched quartic polynomial, ROUND-wrapped to 3 digits. All computed
      cells are Excel formulas — never precomputed Python values. Polynomial
      constants and the 40-210 (M) / 40-150 (F) bodyweight clamp are loaded from
      references/dots_formula.md and embedded directly in the script.
    script: scripts/build_dots_workbook.py
    inputs:
      - name: input-path
        type: string
      - name: output-path
        type: string
      - name: selected-columns
        type: list[object]
      - name: data-row-count
        type: integer
    outputs:
      - name: output-path
        type: string
      - name: rows-written
        type: integer

  - name: verify-output
    description: >
      Re-open the written workbook with openpyxl (formulas preserved) and assert:
      the Dots sheet exists, header row equals the expected 8 headers in order,
      TotalKg and Dots cells in row 2 are stored as formula strings (not values),
      and the Dots formula references the Sex, BodyweightKg, and TotalKg cells in
      the same row. Any failure means a write-path bug — fix the script and re-run
      build-dots-sheet rather than patching the output.
    script: scripts/verify_output.py
    inputs:
      - name: output-path
        type: string
    outputs:
      - name: ok
        type: boolean
      - name: notes
        type: list[string]

search_shortcuts:
  - category: Reference Documents
    body: |
      - references/dots_formula.md — canonical Dots polynomial, sex-specific
        coefficients (M and F), bodyweight clamp ranges, and worked numeric
        examples for sanity-checking output values.
      - references/openipf_data_columns.md — OpenPowerlifting Data-sheet
        column dictionary; covers mandatory vs optional fields and the
        semantics of each value (Sex, Event, Equipment, lift columns).
      - references/excel_formula_patterns.md — xlsxwriter recipes for
        cross-sheet references, sex-switched IF expressions, ROUND wrappers,
        and the inline-script PEP 723 metadata used by the scripts here.
  - category: Tooling
    body: |
      - Reading the input workbook: polars + fastexcel (matches the
        OpenPowerlifting reference solution; `pl.read_excel` returns a
        DataFrame whose `.columns` and `.height` give the header row and
        row count directly).
      - Writing formulas: xlsxwriter via `worksheet.write_formula`.
        Prefer xlsxwriter over openpyxl for formula-string handling — no
        quoting surprises with the POWER/MAX/MIN/IF chain.
      - Reading back to verify: openpyxl in default mode (data_only=False)
        so formula strings round-trip unchanged.

scenarios:
  - need: OpenIPF workbook at /root/data/openipf.xlsx with a populated "Data" sheet and an empty "Dots" sheet; instruction asks for 3-digit Dots.
    context: inspect-workbook confirms the Data sheet has the standard OpenPowerlifting columns including Name (A), Sex (B), BodyweightKg (I), Best3SquatKg (K), Best3BenchKg (L), Best3DeadliftKg (M).
    action: select-dots-columns picks A, B, I, K, L, M and maps them to Dots A..F. build-dots-sheet writes cross-sheet refs for A..F, =D{row}+E{row}+F{row} for G, and the sex-switched ROUND(IF(...),3) polynomial for H.
    outcome: Output workbook recomputes correctly when opened in Excel; verify-output reports ok=true with no notes.
  - need: Same workbook but the instruction says "overwrite the original".
    context: scope_and_approval allows this when explicitly requested.
    action: build-dots-sheet writes to a temp path, verify-output passes, then move/rename the temp over the original path.
    outcome: Original file replaced with the formula-populated workbook; no data loss because verification ran first.
  - need: Workbook is OpenIPF-shaped but Sex column contains "Mx" rows.
    context: The Dots formula is defined only for M and F. Mx falls back to the female polynomial in the canonical IF expression (any non-"M" → female branch).
    action: Proceed with the standard formula; surface to the user that Mx rows are being scored on the female polynomial by convention and ask whether to filter them.
    outcome: User decides whether to keep or drop Mx rows; the formula is unchanged.

anti_patterns:
  - Precomputing TotalKg or Dots in Python and writing raw numbers to the Dots sheet. The instruction requires Excel *formulas* — the workbook must recompute on edit, and a values-only output will fail verification.
  - Forgetting the bodyweight clamp. Male clamp is 40-210, female is 40-150. Skipping it silently produces wildly wrong values for outliers near the polynomial tails.
  - Hard-coding a single Sex branch. The formula must IF-switch on the Sex cell of *each row* so the correct polynomial is picked per lifter.
  - ROUND-wrapping the inner polynomial. ROUND wraps only the final IF expression at 3 digits; rounding earlier loses precision.
  - Reordering or renaming the copied columns. The Dots sheet preserves the source column order and header text exactly as they appear in Data.
  - Treating the original SKILL.md's generic sections (Tech Stack, Performance Targets, Senior-Level Responsibilities) as task-relevant. They are background framing; the Dots-specific procedure above is what actually closes the task.
  - Using openpyxl to write the formulas. It works but quoting and force-recalc behavior are inconsistent across Excel versions; xlsxwriter's write_formula is the tested path.
```
