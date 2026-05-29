---
name: senior-data-scientist
description: Data-science skill for sports-analytics spreadsheet workflows — specifically, computing IPF/OpenPowerlifting Dots coefficients in Excel by writing formula cells (not pre-computed values) referencing a source data sheet. Covers the OpenIPF column schema, the sex-conditional Dots polynomial with bodyweight clamps, three-digit precision via ROUND, and the xlsxwriter pattern for building a workbook whose cells openpyxl reads back as formulas. Use when the user mentions powerlifting, Dots / IPF / OpenPowerlifting coefficients, `openipf.xlsx`, lifter scoring, or asks to populate an empty sheet with Excel formulas that reference another sheet.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.12+ with uv, and the packages polars, xlsxwriter, fastexcel. Designed for the OpenPowerlifting Dots formula on workbooks following the OpenIPF column schema.
---

```yaml
purpose: >
  Compute IPF/OpenPowerlifting Dots coefficients on a powerlifting results
  workbook by writing Excel formulas (not pre-computed numbers) into an empty
  Dots sheet that references the populated Data sheet. The skill encodes the
  sex-conditional Dots polynomial, the bodyweight clamps, three-digit
  precision via ROUND, and the xlsxwriter pattern needed so the output cells
  read back as formulas under openpyxl inspection.

trigger_when:
  - User references `openipf.xlsx`, the OpenIPF/OpenPowerlifting dataset, or
    asks to compute Dots / Wilks / lifter scoring coefficients.
  - User asks to populate an empty sheet with Excel formulas referencing
    another sheet (cross-sheet `=Sheet!Ref` pattern).
  - Task instruction mentions a "Dots" sheet, `Best3SquatKg` /
    `Best3BenchKg` / `Best3DeadliftKg` columns, or `BodyweightKg` + `Sex`.
  - User asks for sex-conditional bodyweight-adjusted strength scoring with
    fixed precision.

do_not_use_when:
  - The user wants pre-computed numeric Dots values (e.g. a CSV report) and
    explicitly does not want Excel formulas — this skill always emits
    formulas to satisfy a `=`-prefix verifier.
  - The task is generic data-science / MLOps work (model training,
    deployment, monitoring) unrelated to spreadsheet scoring.
  - The user wants a different scoring system (Wilks, GL points, IPF GL) —
    the polynomial coefficients here are Dots-specific.

scope_and_approval: >
  Read-only on the input workbook until the build step. The build step
  writes a new `.xlsx` and may overwrite the input path on completion when
  the task expects the result in place. Confirm the output path with the
  user before overwriting if the path is ambiguous; otherwise proceed.

steps:
  - name: read-instruction-and-schema
    description: >
      Read the task instruction (e.g. `/root/data/data-readme.md` or
      `instruction.md`) and `references/openipf-data-schema.md` to confirm
      the sheet names ("Data", "Dots"), the columns present on Data, and
      the target column layout on Dots. Do not hard-code column letters —
      map by header name.
    outputs:
      - name: sheet-plan
        type: object
        description: Sheet names and the header-to-column-letter map for Data.

  - name: identify-needed-columns
    description: >
      From the Data sheet headers, identify the six columns required for
      Dots computation: Name, Sex, BodyweightKg, Best3SquatKg, Best3BenchKg,
      Best3DeadliftKg. If any header is missing, stop and report which —
      do not attempt fuzzy matching.
    inputs:
      - name: sheet-plan
        type: object
    outputs:
      - name: column-plan
        type: object
        description: Map of Dots-sheet target column → source Data-sheet column.

  - name: review-dots-formula
    description: >
      Read `references/dots-formula.md` before constructing any formula by
      hand. The polynomial has two coefficient sets (M, F) and two
      bodyweight clamps (40–210, 40–150). Mismatching a clamp with the
      wrong coefficient set is a common, silent failure.
    inputs:
      - name: column-plan
        type: object
    outputs:
      - name: formula-spec
        type: object
        description: Confirmed coefficient sets, clamps, and ROUND precision.

  - name: build-workbook
    description: >
      Rebuild the workbook with `scripts/dots_formula.py build`. The script
      recreates the Data sheet verbatim, then writes the Dots sheet with
      eight headers and formula cells in each row: cross-sheet refs for the
      six copied columns, `=D{r}+E{r}+F{r}` for TotalKg, and the
      `ROUND(IF(Sex="M", ..., ...), 3)` Dots formula. Uses xlsxwriter so
      cells round-trip as formulas under openpyxl.
    script: scripts/dots_formula.py
    inputs:
      - name: formula-spec
        type: object
    outputs:
      - name: workbook-path
        type: string
        description: Path to the rebuilt workbook.

  - name: verify-output
    description: >
      Re-open the output workbook and confirm: Dots sheet exists; headers
      match the expected eight in order; row count equals the Data sheet;
      `G2` and `H2` are strings starting with `=`; `H2` contains both
      `ROUND(` and `IF(`. Read `references/excel-formula-patterns.md` if
      any cell read-back returns a numeric value instead of a formula —
      that means the writer library serialized the cell wrong.
    inputs:
      - name: workbook-path
        type: string
    outputs:
      - name: verification-result
        type: object
        description: Pass/fail with the specific check that failed, if any.

  - name: place-output
    description: >
      If the task expects the result at the original input path (e.g.
      `/root/data/openipf.xlsx`), move the rebuilt workbook over the input
      path. Otherwise leave it at the build output path and report the
      location.
    inputs:
      - name: workbook-path
        type: string
      - name: verification-result
        type: object
    outputs:
      - name: final-path
        type: string

search_shortcuts:
  - category: Domain references
    body: |
      - `references/dots-formula.md` — Coefficients, clamps, full Excel
        formula shape. Read before constructing any Dots formula by hand.
      - `references/openipf-data-schema.md` — Column-by-column meaning of
        the OpenIPF data sheet and target Dots-sheet layout.
      - `references/excel-formula-patterns.md` — Library choice
        (xlsxwriter > openpyxl > polars), index conventions, and the
        verifier's formula-string checks.
  - category: Upstream sources
    body: |
      - OpenPowerlifting Dots crate:
        https://gitlab.com/openpowerlifting/opl-data/-/tree/main/crates/coefficients/src
      - OpenPowerlifting data schema:
        https://gitlab.com/openpowerlifting/opl-data/blob/main/docs/data-readme.md

scenarios:
  - need: >
      "Calculate the Dots score for every lifter in `/root/data/openipf.xlsx`
      and write the formulas into the empty Dots sheet."
    context: >
      Data sheet uses the standard OpenIPF column order; Dots sheet is empty
      with no headers. Verifier checks formula cells via openpyxl.
    action: >
      Read instruction + schema → run `python scripts/dots_formula.py build
      --input /root/data/openipf.xlsx --output /root/data/openipf.xlsx`.
    outcome: >
      Dots sheet populated with 8 headers and one formula row per Data row;
      `G2` and `H2` are formula strings; computed values match ground truth
      within 0.01.

  - need: >
      "I just want to see the Dots formula for one cell — I'll splice it
      into my own workbook."
    action: >
      `python scripts/dots_formula.py formula --sex B2 --bw C2 --total G2`
      prints the formula string to stdout.
    outcome: One Excel-ready formula string, no workbook side effects.

anti_patterns:
  - Hand-authoring the Dots polynomial in chat. The clamp bounds and
    coefficient sets are easy to swap — use the script.
  - Pre-computing Dots values in Python and writing numbers to the cells.
    The verifier rejects any `H2` value that does not start with `=`.
  - Using `polars.write_excel` to build the output — it serializes computed
    values, not formulas. Use `xlsxwriter` (see
    `references/excel-formula-patterns.md`).
  - Hard-coding column letters (`Data!I{row}`) when the input workbook
    might reorder columns. Map by header name; the bundled script does this.
  - Wrapping the Dots formula in `IFERROR(...)` "defensively." The cleaned
    task input has all required fields populated and the verifier compares
    against ground truth — silently swallowing an error hides correctness
    bugs.
  - Treating this as a generic data-science task. The original curated
    skill suggested PyTorch / Spark / MLflow / K8s — none apply. The work
    is a sub-minute spreadsheet rebuild.
```
