---
name: protein-expression-xlsx
description: Fill a protein expression analysis Excel template (.xlsx) with live formulas - INDEX/MATCH lookups of expression values from a Data sheet into yellow cells, Control vs Treated mean and standard deviation per protein, fold change and log2 fold change, and a ranking of top up/down-regulated proteins - then recalculate with LibreOffice and verify zero formula errors. Use for proteomics/gene-expression spreadsheet tasks (Protein_ID, Gene_Symbol, sample columns, CCLE TMT log2 data) and as a general guide for formula-driven xlsx editing with openpyxl.
license: Proprietary. source/xlsx/LICENSE.txt has complete terms
compatibility: Python 3 with openpyxl; LibreOffice (soffice) for recalculation. pandas is not required.
metadata:
  aip-version: "0.5a1"
---

# AIP runtime — format 0.5a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the JSON object a step receives. Each step declares its required keys as `inputs`; extra keys pass through.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the final state's shape.

## Execution

The state is one JSON object. It starts as the start step's `inputs` and flows along `inputs_to`; each step's output is merged over it, so keys accumulate and extra keys pass through untouched. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. You may change the state before any step runs; you have the final say at every step.

- **`execution`**: run `script` with one JSON object on stdin, `{"currentState": <state>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout; merge it over the state.
- **`decision`**: answer each question against the state. Each answer collapses to one value under its question name and is merged over the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the state, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the next step's `inputs`; merge them over the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. That state is the procedure's result.

```yaml
purpose: >
  Complete a protein-expression workbook template end to end: map its layout (task sheet,
  Data sheet, yellow input cells, Control/Treated sample columns, statistic rows, fold-change
  table), write live Excel formulas for the lookups, group means and SDs, fold changes and a
  |log2 FC| ranking, recalculate with LibreOffice so cached values exist, and verify every
  formula against an independent Python computation. It encodes what agents get wrong unaided:
  stale cell ranges in sheet instructions, blank data cells that INDEX turns into 0, already-log2
  data that must be subtracted not divided, SD of fewer than two values, #NAME? from modern
  function names, and formulas left uncalculated.

trigger_when:
  - A task asks to fill yellow cells in an .xlsx by looking up protein or gene expression values from a data sheet.
  - A spreadsheet needs Control vs Treated means, standard deviations, fold change or log2 fold change per protein.
  - A task asks to identify top up- or down-regulated proteins in an Excel workbook.
  - Any expression-matrix workbook (Protein_ID / Gene_Symbol rows, sample columns) must be analysed with Excel formulas rather than hardcoded numbers.

do_not_use_when:
  - The analysis needs statistical testing (t-tests, p-values, FDR) or normalisation rather than template filling; use a statistics workflow instead.
  - The input is a CSV/TSV to analyse without an Excel deliverable.
  - The workbook is a financial model or other non-expression spreadsheet; follow references/xlsx-guide.md directly instead.

steps:
  - name: inspect
    kind: execution
    description: Map the workbook layout from labels and yellow fills, check IDs and sample names against the Data sheet, and profile the data scale and missing values.
    inputs:
      - name: workbook_path
        type: string
        description: Absolute path to the task workbook (in the task container usually /root/protein_expression.xlsx).
      - name: output_path
        type: string
        description: Where to save the result. Use the path the task names; when it names none, the input path itself (edit in place).
      - name: task_instructions
        type: string
        description: The task statement as given, verbatim. Its cell ranges and requirements override the sheet's own instruction text.
    script: scripts/inspect_workbook.py
    timeout: 120
    inputs_to: assess

  - name: assess
    kind: decision
    description: Settle the data scale, SD type, whether a ranking table is wanted, and whether the detected layout can be trusted.
    inputs:
      - name: layout
        type: object
        description: Detected cell map (sheets, rows, columns, statistic rows, fold-change table, data bounds, per-protein missing counts).
      - name: scale_hint
        type: object
        description: Data value profile - min, max, median, fraction negative, blank count.
      - name: layout_warnings
        type: list[*]
        description: Problems inspect found, including sheet instruction ranges that disagree with the yellow cells.
      - name: sheet_instructions
        type: list[*]
        description: Instruction text found on the task sheet.
      - name: task_instructions
        type: string
    questions:
      data_scale:
        type: choice
        instructions: >
          Are the Data sheet values already log2-transformed or linear? Judge from scale_hint and any wording in
          the task. Many negative values, a median near 0 and a range of roughly -15 to +8 (typical CCLE TMT
          relative abundance) mean log2. Follow an explicit statement in the task over the profile.
        criteria:
          log2: Values centred near 0 with many negatives, or the task says log2/log-transformed. Log2 FC = treated mean - control mean; FC = 2^Log2 FC.
          linear: All values positive and spread over orders of magnitude (raw intensities, counts), or the task says linear. FC = treated mean / control mean; Log2 FC = log2(FC).
      stdev_kind:
        type: choice
        instructions: Which standard deviation does the task want? Replicate samples default to the sample SD unless the task explicitly asks for population SD (STDEV.P, STDEVP, divide by n).
        criteria:
          sample: Sample SD with n-1 (Excel STDEV / STDEV.S). The default.
          population: Population SD with n (Excel STDEVP / STDEV.P), only when explicitly requested.
      add_top_table:
        type: noul
        instructions: >
          Does the task or the sheet's instruction text ask to identify, rank or list the top regulated
          (up/down) proteins? If yes, a ranking table is written below the fold-change table (or into a
          labelled template region if layout.top_table.existing_template is true).
      layout_ok:
        type: noul
        instructions: >
          Is the detected layout complete and consistent, so formulas can be written as mapped? True when
          protein_rows, control_cols, treated_cols, all four stats_rows, stat_cols (one per protein) and the
          fold_change table with fc_col and log2_col are present, and every warning is only a stale sheet
          instruction range. False for any other warning (missing IDs or sample names, unrecognised groups,
          missing statistic rows or fold-change columns, non-yellow lookup cells) or when task_instructions
          name cells that differ from the mapped ones.
        criteria:
          true: Layout complete; only stale-instruction-range warnings, which are expected and ignored.
          false: Any structural warning, or the task's own instructions point at different cells.
    thresholds:
      data_scale: 0.8
      layout_ok: 0.2
      add_top_table: 0.2
    inputs_to: layout-gate

  - name: layout-gate
    kind: router
    description: A trusted layout goes straight to formula writing; anything else is corrected by hand first.
    branch_on: layout_ok
    branches:
      "true": build
      "false": fix-layout

  - name: fix-layout
    kind: client_task
    description: Inspect the sheet yourself and correct the layout object so every formula lands in the intended cells.
    inputs:
      - name: workbook_path
        type: string
      - name: layout
        type: object
      - name: layout_warnings
        type: list[*]
      - name: sheet_instructions
        type: list[*]
      - name: task_instructions
        type: string
    template: assets/fix_layout.md
    references:
      - path: references/protein-fold-change.md
        description: Data-scale, missing-value and SD rules; load if the groups or scale are unusual.
    inputs_to: build

  - name: build
    kind: execution
    description: Write lookup, statistic, fold-change and ranking formulas into the template, save to output_path, and compute the same values in Python as the expected results.
    inputs:
      - name: workbook_path
        type: string
      - name: output_path
        type: string
      - name: layout
        type: object
      - name: data_scale
        type: string
        description: log2 or linear.
      - name: stdev_kind
        type: string
        description: sample or population.
      - name: add_top_table
        type: boolean
    script: scripts/build_formulas.py
    timeout: 120
    inputs_to: verify

  - name: verify
    kind: execution
    description: Recalculate the saved workbook with LibreOffice (scripts/recalc.py), scan every cell for formula errors, confirm formulas survived, and compare cached values with the expected results.
    inputs:
      - name: output_path
        type: string
      - name: layout
        type: object
      - name: expected
        type: object
        description: Cell address to the value the formula must produce (null = blank).
    script: scripts/verify_workbook.py
    timeout: 300
    inputs_to: verify-gate

  - name: verify-gate
    kind: router
    description: Clean output goes to the report; formula errors, mismatches or a missing recalculation go to repair.
    branch_on: verify_status
    branches:
      ok: report
      errors_found: fix-output
      mismatch: fix-output
      recalc_failed: fix-output
      recalc_unavailable: fix-output

  - name: fix-output
    kind: client_task
    description: Diagnose and repair the failed verification (recalculation, formula errors, wrong mappings), then re-verify or declare it unresolved.
    inputs:
      - name: output_path
        type: string
      - name: verify_status
        type: string
      - name: verify_report
        type: object
      - name: build_notes
        type: list[*]
    template: assets/fix_output.md
    references:
      - path: references/xlsx-guide.md
        description: General openpyxl/formula rules, recalc.py usage and output format, error checklist; load when repairing formulas or recalculation.
      - path: references/protein-fold-change.md
        description: Domain rules for scale, missing values, SD and ranking; load when a mismatch looks like a method question rather than a mapping bug.
    inputs_to: after-fix

  - name: after-fix
    kind: router
    description: Re-verify after a repair; report an unresolvable problem honestly.
    branch_on: fix_outcome
    branches:
      refixed: verify
      unresolved: report

  - name: report
    kind: client_task
    description: Summarise where results were written, the method, the top regulated proteins and any caveats.
    inputs:
      - name: output_path
        type: string
      - name: verify_status
        type: string
      - name: data_scale
        type: string
      - name: stdev_kind
        type: string
      - name: results
        type: list[*]
      - name: top_regulated
        type: list[*]
      - name: build_notes
        type: list[*]
    template: assets/report.md
    references:
      - path: references/protein-fold-change.md
        description: How to interpret log2 FC, direction, two-fold cut-off and weak low-n estimates.
    inputs_to: end

  - name: end
    kind: end
    description: The filled, recalculated workbook at output_path plus a written summary.
    inputs:
      - name: output_path
        type: string
      - name: verify_status
        type: string
      - name: top_regulated
        type: list[*]
      - name: final_summary
        type: string

anti_patterns:
  - Writing into the ranges quoted in the sheet's instruction text (e.g. "H7:BB16") when the yellow cells and labels sit elsewhere; those ranges are often stale.
  - Computing means or fold changes in Python and pasting numbers; every result cell must be a live formula.
  - Plain INDEX/MATCH lookups that turn blank data cells into 0 and drag means toward 0; blanks must stay blank.
  - Dividing means of log2 data or taking log2 of a ratio of negative numbers; for log2 data subtract the means.
  - Using STDEV.S/STDEV.P without the _xlfn. prefix (shows #NAME?) or letting STDEV run on fewer than two values (#DIV/0!).
  - Delivering without recalculation; openpyxl leaves formulas without cached values, so readers using data_only=True see empty cells.
  - Saving a workbook loaded with data_only=True, which permanently replaces formulas with values.
  - Restyling the template; keep its fills, fonts and layout and only fill the intended cells.
  - Assuming pandas is installed in the task container; use openpyxl.
```
