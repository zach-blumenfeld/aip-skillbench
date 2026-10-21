---
name: powerlifting-score-sheet
description: Compute powerlifting relative-strength scores (Dots, Wilks, IPF GL / Good Lift; Glossbrenner by hand) for every lifter in an OpenPowerlifting/OpenIPF-style Excel workbook, as live Excel formulas. Copies only the columns the score needs (Name, Sex, BodyweightKg, Best3SquatKg, Best3BenchKg, Best3DeadliftKg, plus Event/Equipment for IPF GL) into the score sheet in the data sheet's order, appends a TotalKg formula and a score formula with the official coefficients, sex mapping (M/Mx men, F women), bodyweight clamps and rounding, then recalculates with LibreOffice and verifies every value. Use for "calculate Dots/Wilks/GL coefficients for each competitor in openipf.xlsx", powerlifting coefficient or points spreadsheets, and IPF/OpenPowerlifting score columns.
compatibility: Python 3.10+ with openpyxl. Recalculation uses LibreOffice (soffice) or gnumeric (ssconvert) when present; without one, formulas are written but values stay uncached.
metadata:
  aip-version: "0.6a1"
  version: "1.0"
---

# AIP runtime — format 0.6a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the one JSON object a run carries. Each step declares the keys it reads as `inputs`; `execution` and `client_task` steps declare the keys they add as `outputs`, and a `decision` adds one key per question.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the procedure's result.

## Execution

The state starts as the start step's `inputs` and flows along `inputs_to`; each step adds its outputs to it. Every key is produced by exactly one step, so keys accumulate and nothing is overwritten. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. A step sees only those keys: give it its declared `inputs` and nothing else from the state. You have the final say at every step.

- **`execution`**: before the first one, check that this machine has everything `requires` names (the interpreter at its minimum version, the packages, the tools); if anything is missing, stop and name all of it. Run `script` from its folder, launched with the step's `command` when it has one and `python <script>` otherwise, with one JSON object on stdin, `{"state": <the step's inputs>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout holding exactly the step's `outputs`; add them to the state. A non-zero exit, or output missing a declared key, fails the step: stop there and report it rather than doing the step by hand.
- **`decision`**: answer each question from the step's inputs, and from the run so far only when the step sets `history: true`. Each answer collapses to one value under its question name and is added to the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the step's inputs, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the step's `outputs`; add them to the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. Those keys are the procedure's result.

```yaml
purpose: >
  Turn a workbook of powerlifting meet results (OpenPowerlifting/OpenIPF columns) into a score sheet
  that computes each lifter's total and relative-strength score with live Excel formulas. Carries the
  OpenPowerlifting Dots, Wilks and IPF GL parameters, the sex/equipment/event mappings, bodyweight
  clamps and zero rules, the column-selection rule (only what the score needs, plus Name, in the data
  sheet's order and names), and the xlsx rules (formulas not hardcoded values, zero formula errors,
  recalculate before values are read). A script writes and verifies the sheet; the agent only judges
  which score and precision the task asks for and repairs the workbook if the check fails.

trigger_when:
  - A task asks to calculate Dots, Wilks, IPF GL (Good Lift) or Glossbrenner scores or coefficients for lifters in an Excel workbook.
  - A workbook has OpenPowerlifting/OpenIPF columns (Name, Sex, BodyweightKg, Best3SquatKg, Best3BenchKg, Best3DeadliftKg) and an empty sheet to fill with totals and scores.
  - Someone needs powerlifting totals or bodyweight-normalised points added to a spreadsheet as Excel formulas.

do_not_use_when:
  - The scores are wanted only as a number in chat or a CSV with no workbook formulas; compute them directly from references/scoring-formulas.md.
  - The task is general spreadsheet work unrelated to powerlifting scoring.
  - The data is weightlifting (snatch / clean and jerk, Sinclair), not powerlifting.

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - openpyxl

steps:
  - name: identify-score
    kind: decision
    description: Read the task statement to settle which powerlifting score to build and how many decimals to round to.
    inputs:
      - name: task_statement
        type: string
        description: The task text as given, verbatim, including any precision or column-naming instructions.
      - name: workbook_path
        type: string
        description: Absolute path of the workbook to edit in place (e.g. /root/data/openipf.xlsx). Not judged here; carried for later steps.
    questions:
      score_system:
        type: choice
        instructions: >
          Which score does the task ask to compute for each lifter? Judge from the task statement only;
          a link to a Dots guide or the word "Dots" means dots. A request for several scores at once,
          or for an age-adjusted (McCulloch, masters) score, is other.
        criteria:
          dots: Dots / DOTS (Dynamic Objective Team Scoring) points or coefficients.
          wilks: Wilks points or coefficients (original Wilks, not Wilks2020).
          ipf_goodlift: IPF GL, IPF Good Lift, IPF GOODLIFT points or the IPF GL coefficient.
          other: Glossbrenner, Wilks2020, IPF Points (pre-2020), Schwartz/Malone, age-adjusted scores, several scores, or anything else.
      decimals:
        type: score
        instructions: >
          To how many decimal places must computed values be rounded? Read phrases like "keep 3 digits
          precision" or "round to two decimals" as that number of decimal places. If the task states no
          precision, answer level 3.
        criteria:
          - 0 decimals (whole numbers).
          - 1 decimal place.
          - 2 decimal places.
          - 3 decimal places ("3 digits precision"), or no precision stated.
          - 4 decimal places.
          - 5 decimal places.
          - 6 decimal places.
    thresholds:
      score_system: 0.8
      decimals: 0.7
    inputs_to: by-score-system

  - name: by-score-system
    kind: router
    description: Dots, Wilks and IPF GL are built by the script; anything else is built by hand.
    branch_on: score_system
    branches:
      dots: build-score-sheet
      wilks: build-score-sheet
      ipf_goodlift: build-score-sheet
      other: manual-score-sheet

  - name: build-score-sheet
    kind: execution
    description: >
      Find the data sheet (prefers "Data"), copy Name plus the score's needed columns in the data sheet's
      order and names into the sheet named for the score (Dots / Wilks / Goodlift; created if absent,
      cleared if it has content), append TotalKg =ROUND(SUM(squat,bench,deadlift),decimals) and the score
      formula, save in place (backup in a temp dir), recalculate with LibreOffice or gnumeric, and verify
      every cached value against an independent Python computation.
    inputs:
      - name: workbook_path
        type: string
      - name: score_system
        type: string
      - name: decimals
        type: integer
    script: scripts/build_score_sheet.py
    assets:
      - assets/coefficients.json
    timeout: 600
    outputs:
      - name: score_sheet
        type: string
        description: Title of the sheet that now holds the scores.
      - name: copied_columns
        type: list[*]
        description: Column headers copied from the data sheet, in order, before TotalKg and the score column.
      - name: formula_examples
        type: object
        description: The TotalKg and score formulas written in row 2.
      - name: rows_written
        type: integer
        description: Number of lifter rows written.
      - name: recalc_status
        type: string
        description: verified, not_recalculated, formula_errors, or mismatch.
      - name: check_report
        type: object
        description: Engine used, error and mismatch cells, max difference, data anomalies, notes, backup path, sample rows.
    inputs_to: by-check

  - name: by-check
    kind: router
    description: A verified sheet is done; any other status goes to repair.
    branch_on: recalc_status
    branches:
      verified: end
      not_recalculated: fix-workbook
      formula_errors: fix-workbook
      mismatch: fix-workbook

  - name: fix-workbook
    kind: client_task
    description: Recalculate or repair the score sheet until the verify check passes, keeping formulas.
    inputs:
      - name: workbook_path
        type: string
      - name: score_sheet
        type: string
      - name: formula_examples
        type: object
      - name: recalc_status
        type: string
      - name: check_report
        type: object
      - name: score_system
        type: string
      - name: decimals
        type: integer
    template: assets/fix-workbook.md
    references:
      - path: references/xlsx-rules.md
        description: recalc.py usage and output, LibreOffice/gnumeric alternatives, openpyxl data_only trap, formula-error causes. Load when recalculation fails or errors are reported.
      - path: references/scoring-formulas.md
        description: Coefficients, clamps, sex/equipment/event mappings and published check values. Load when a cached value mismatches.
    outputs:
      - name: fix_summary
        type: string
        description: What was wrong, what was changed, and the final verify status.
    inputs_to: end

  - name: manual-score-sheet
    kind: client_task
    description: Build a score sheet the script does not cover (e.g. Glossbrenner) by hand with Excel formulas.
    inputs:
      - name: task_statement
        type: string
      - name: workbook_path
        type: string
      - name: decimals
        type: integer
    template: assets/manual-score-sheet.md
    references:
      - path: references/scoring-formulas.md
        description: Dots, IPF GL, Wilks and Glossbrenner formulas with parameters, clamps, zero rules, check values, and the OpenPowerlifting column meanings. Load first.
      - path: references/xlsx-rules.md
        description: Workbook rules (formulas not values, zero errors, preserve existing format) and how to recalculate with scripts/recalc.py. Load before saving.
    outputs:
      - name: manual_summary
        type: string
        description: Sheet and columns written, formula used, recalc result, and anything not done.
    inputs_to: end

  - name: end
    kind: end
    description: The workbook at workbook_path now holds the score sheet with TotalKg and score formulas.
    inputs:
      - name: workbook_path
        type: string
      - name: score_system
        type: string

anti_patterns:
  - Computing totals or scores in Python and writing numbers into cells; every TotalKg and score cell must be an Excel formula.
  - Copying columns the score does not use (Age, Division, Place, Federation...) or reordering or renaming the copied ones; copy Name plus exactly the needed columns, in the data sheet's order with its header text.
  - Copying a TotalKg column that already exists in the data; recompute it with a formula appended after the copied columns.
  - Putting the score before TotalKg, or naming the columns anything other than TotalKg and the score name the task uses (Dots).
  - Using women's coefficients for Mx lifters; M and Mx use the men's parameters, only F uses the women's.
  - Skipping the bodyweight clamp (Dots men 40-210 kg, women 40-150 kg) or letting a blank bodyweight or zero total produce #DIV/0! instead of 0.
  - Leaving formulas uncalculated; openpyxl stores no values, so recalculate (LibreOffice) before anyone reads the file with data_only.
  - Saving a workbook opened with data_only=True, which destroys every formula.
  - Hand-building Dots, Wilks or IPF GL when the script supports them, or inventing missing coefficients (e.g. Schwartz/Malone for Glossbrenner).
```
