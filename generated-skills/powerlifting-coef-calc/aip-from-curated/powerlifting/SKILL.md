---
name: powerlifting
description: "Calculating powerlifting scores (DOTS, Wilks, IPF GoodLift, Glossbrenner) to determine the performance of lifters across different weight classes. Use when the user asks to compute, normalize, rank, or compare powerlifting totals; or when an Excel/CSV of lifters needs a coefficient column added; or when a powerlifting federation result needs to be made comparable across body weights or sexes."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: "Designed for Claude Code or similar agentic runtimes. Requires python3 and openpyxl (3.x). uv is convenient but not required."
---

```yaml
purpose: >
  Compute and persist powerlifting normalization coefficients (DOTS,
  Wilks, IPF GoodLift, or Glossbrenner) for a roster of lifters. The
  procedure inspects an input spreadsheet, picks the right formula
  family from sex/equipment/event, and writes the result back as
  Excel formulas — so the workbook stays "live" and downstream
  consumers (and graders) see formula references, not literals.

trigger_when:
  - User asks to "compute DOTS", "rank by Wilks", "add an IPF GL column", or otherwise normalize a powerlifting total.
  - An Excel/CSV of lifters needs a coefficient column added next to TotalKg.
  - A federation result needs to be made comparable across weight classes or sexes.
  - The task gives an `openipf`-style workbook with a `Data` sheet and an empty target sheet to be populated.

do_not_use_when:
  - The user only wants the raw 3-lift total with no normalization — that is a single SUM and does not need this skill.
  - The user asks for age-adjusted scoring (e.g. McCulloch / Foster age coefficients). The four formulas here normalize for bodyweight, not age.
  - The dataset is not powerlifting (Olympic weightlifting uses Sinclair, not DOTS/Wilks/GL).

scope_and_approval: >
  Read-only on the source sheet — the procedure never edits incoming lifter
  records. The target sheet is dropped and recreated on each run; warn the
  user before overwriting a target sheet that already contains data. Writes
  go through `scripts/build_coef_workbook.py`, which respects the input and
  output paths the agent supplies (set them to the same path for an
  in-place update, as the curated openipf task expects).

steps:
  - name: inspect-workbook
    description: >
      Open the input `.xlsx` and report sheet names, the source sheet's
      header row, and row count. Confirm which sheet is the source of
      lifter records and which sheet (often empty) is the target.
    outputs:
      - name: source-sheet
        type: string
        description: Name of the sheet holding lifter records (commonly "Data").
      - name: target-sheet
        type: string
        description: Name of the sheet to populate (commonly "Dots").
      - name: header-row
        type: list[string]
        description: Column headers from the source sheet, in order.
      - name: row-count
        type: integer
  - name: choose-coefficient
    description: >
      Pick exactly one normalization family — value passed as `--coef` to
      the build script. `dots` is the modern default and the curated
      openipf task's required output; `wilks` is requested by older
      federations and some classic competitions; `goodlift` is the IPF
      GoodLift formula (current IPF standard, needs event + equipment);
      `glossbrenner` is the GPC standard and is best-effort here (see
      `references/glossbrenner.md`).
    one_of:
      - dots
      - wilks
      - goodlift
      - glossbrenner
    inputs:
      - name: header-row
        type: list[string]
    outputs:
      - name: coef
        type: string
      - name: equipment
        type: string
        nullable: true
        description: IPF GoodLift only — Raw or Single (Wraps/Straps fold into Raw; Multi/Unlimited fold into Single).
      - name: event
        type: string
        nullable: true
        description: IPF GoodLift only — SBD (full power) or B (bench only).
  - name: load-coefficient-reference
    description: >
      Read the reference file for the chosen coefficient so the
      formula constants, BW clamps, and edge cases are in context before
      assembling the formula. Files - dots `references/dots.md`,
      wilks `references/wilks.md`, ipf-goodlift `references/ipf-goodlift.md`,
      glossbrenner `references/glossbrenner.md`.
    inputs:
      - name: coef
        type: string
  - name: plan-column-mapping
    description: >
      Map the target sheet's columns back to source-sheet column letters.
      The required headers — Name, Sex, BodyweightKg, Best3SquatKg,
      Best3BenchKg, Best3DeadliftKg — must all be present and in the
      order the user/task requested for the target sheet. Use the
      header-row indices observed in `inspect-workbook` to derive each
      column letter (A, B, …). Express the result as the comma-separated
      `HEADER=COL` string the build script consumes.
    inputs:
      - name: header-row
        type: list[string]
      - name: target-sheet
        type: string
    outputs:
      - name: columns-arg
        type: string
        description: e.g. `Name=A,Sex=B,BodyweightKg=I,Best3SquatKg=K,Best3BenchKg=L,Best3DeadliftKg=M`
  - name: build-workbook
    description: >
      Invoke the builder. Writes the target sheet with formula references
      to the source sheet, a TotalKg `=Sx+Bx+Dx` formula, and a
      coefficient formula with sex-aware coefficient selection and
      ROUND(…, precision).
    script: scripts/build_coef_workbook.py
    inputs:
      - name: input-path
        type: string
      - name: output-path
        type: string
      - name: source-sheet
        type: string
      - name: target-sheet
        type: string
      - name: coef
        type: string
      - name: precision
        type: integer
        description: Digit precision for the final ROUND. Default 3 — matches the curated openipf task.
      - name: columns-arg
        type: string
      - name: equipment
        type: string
        nullable: true
      - name: event
        type: string
        nullable: true
    outputs:
      - name: workbook-path
        type: string
  - name: verify-output
    description: >
      Open the output workbook with openpyxl and confirm — (1) the target
      sheet exists and has one header row plus `row-count` data rows,
      (2) its column headers match the requested order ending with
      TotalKg and the chosen coefficient name, (3) the TotalKg cell at
      row 2 starts with "=" and references the three lift columns,
      (4) the coefficient cell at row 2 starts with "=" and contains
      ROUND( and (for sex-branching formulas) IF(. Surface any failure
      with the offending cell address.
    inputs:
      - name: workbook-path
        type: string
      - name: target-sheet
        type: string
      - name: row-count
        type: integer

modes:
  - name: in-place
    body: >
      Overwrite the input workbook with the result (input-path equals
      output-path). This is what the curated openipf task expects.
  - name: side-by-side
    body: >
      Write a fresh output file alongside the input. Preferred when the
      input is checked into a repo or otherwise should not be mutated.

scenarios:
  - need: >
      openipf workbook with a Data sheet and an empty Dots sheet; task
      asks for DOTS coefficients with 3-digit precision and Excel
      formulas (not literals).
    context: >
      `inspect-workbook` reports Data columns A=Name, B=Sex, I=BodyweightKg,
      K=Best3SquatKg, L=Best3BenchKg, M=Best3DeadliftKg.
    action: >
      Choose `dots`, skip equipment/event, run `build-workbook` with
      `--columns Name=A,Sex=B,BodyweightKg=I,Best3SquatKg=K,Best3BenchKg=L,Best3DeadliftKg=M`
      and `--precision 3` in in-place mode.
    outcome: >
      Dots sheet has 8 columns (Name, Sex, BodyweightKg, Best3SquatKg,
      Best3BenchKg, Best3DeadliftKg, TotalKg, Dots); cells G2..G(N+1) are
      `=Dx+Ex+Fx` formulas; cells H2..H(N+1) are
      `=ROUND(IF(B…="F", …, …), 3)` formulas referencing the Data sheet
      via columns C and B of the Dots sheet.
  - need: IPF World Open ranking sheet — Raw, full power.
    context: All lifters have Equipment=Raw and Event=SBD; user wants the IPF GoodLift score.
    action: Choose `ipf-goodlift`, pass `--equipment Raw --event SBD`.
    outcome: >
      Goodlift column carries `=ROUND(IF(B…="F", IF(AND(…>=35, denomF>0),
      total*100/denomF, 0), IF(AND(…>=35, denomM>0), total*100/denomM, 0)),
      precision)` per row.
  - need: Old federation result, mixed equipment, classifier still uses Wilks.
    context: The user wants Wilks because their federation has not switched to DOTS.
    action: Choose `wilks`; coefficients and clamps come from the script's WILKS_M / WILKS_F constants.
    outcome: Wilks column carries the degree-5 reverse polynomial wrapped in IF on sex and ROUND on precision.

anti_patterns:
  - >
    Computing the coefficient in Python and pasting the literal numbers
    into the cells. Graders that check for `cell.value.startswith("=")`
    will fail. Always emit formulas.
  - >
    Forgetting the sex-specific BW clamp. Out-of-range bodyweights must
    pin to the clamp boundary (MAX/MIN), not raise or produce huge
    coefficients.
  - >
    Wrapping the entire DOTS/Wilks expression in a bare division without
    the `500/`. The coefficient is `500 / polynomial(BW)`, not
    `1 / polynomial(BW)`.
  - >
    Using "Mx" or other gender-neutral sex codes against the women's
    parameter set. Mx is scored with the men's coefficients in all four
    formulas.
  - >
    Trusting Excel to coerce mismatched cell types. If BodyweightKg is
    blank or text, the polynomial produces #VALUE!. Filter empty/invalid
    rows in the source sheet before running, or wrap the formula in
    IFERROR if blanks should yield 0.
  - >
    Emitting Glossbrenner as a single closed-form Excel formula. The
    Schwartz-Malone helpers it depends on are not bundled here, so the
    Glossbrenner path is best-effort — see `references/glossbrenner.md`.
```
