---
name: protein-expression-analysis
description: Fill a proteomics Excel workbook (Task + Data sheets, e.g. protein_expression.xlsx) with live formulas - two-way INDEX/MATCH lookup of log2 expression values by protein ID and sample name, Control vs Treated mean and standard deviation, log2 fold change and fold change - then recalculate with LibreOffice and verify every value without changing the template's formatting. Use for control-vs-treated differential protein expression tasks in spreadsheets, cancer cell line proteomics xlsx exercises, or any "look up values, compute group statistics and fold changes with formulas" workbook task.
license: Proprietary. source/xlsx/LICENSE.txt has complete terms
metadata:
  aip-version: "0.6a1"
  compiled-from: xlsx
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
  Complete a protein-expression analysis workbook in place with formulas only. A script
  detects the Task/Data layout (target proteins x samples, Control/Treated group row, the
  transposed statistics block, the fold-change block) without assuming fixed addresses;
  a decision settles how blank measurements are treated and whether the detected layout
  matches the task statement; the agent confirms or corrects the layout; a script writes
  INDEX/MATCH lookups, AVERAGE/STDEV group statistics and log2 fold-change formulas,
  recalculates with LibreOffice, and checks every value against an independent Python
  computation plus the template's fills and fonts. Failures route to a repair task.

trigger_when:
  - A task hands over an .xlsx with a "Task" sheet to fill and a "Data" sheet of expression values (proteins x samples).
  - Expression values must be looked up by protein ID and sample name (two-way lookup) into highlighted cells.
  - Control vs Treated means, standard deviations, log2 fold change and fold change must be computed with spreadsheet formulas.
  - Quantitative proteomics or other log2-transformed omics data in Excel needs a differential-expression summary that stays formula-driven.

do_not_use_when:
  - The deliverable is a statistics report, plot, or CSV produced in Python rather than formulas inside the workbook.
  - The task needs p-values, t-tests, or multiple-testing correction in the sheet (this procedure stops at mean, stdev and fold change).
  - The data are raw intensities that still need log transformation or normalisation before analysis.

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - openpyxl>=3.1
  tools:
    - soffice

steps:
  - name: inspect-layout
    kind: execution
    description: Locate the Task lookup block, group row, statistics block, fold-change block and Data headers; resolve every protein and sample name; profile blank measurements.
    inputs:
      - name: workbook_path
        type: string
        description: Path of the workbook to fill, e.g. /root/protein_expression.xlsx in the task container.
      - name: output_path
        type: string
        description: Where to save the filled workbook. Use the same path as workbook_path to edit in place (the usual deliverable).
      - name: task_instruction
        type: string
        description: The task statement verbatim (which cells to fill, how groups are marked, constraints).
    script: scripts/inspect_layout.py
    timeout: 120
    outputs:
      - name: detected_layout
        type: object
        description: Sheets, Data ranges, lookup rows/columns, group label per sample column, name resolutions, explicit target cell lists for statistics and fold change, and per-protein missing-value counts.
      - name: layout_warnings
        type: list[*]
        description: Anything unexpected - unresolved names, missing labels, non-yellow targets, uncovered yellow cells, blank measurements.
    inputs_to: judge-task

  - name: judge-task
    kind: decision
    description: Decide how blank Data cells are treated and whether the detected layout is the one the task statement describes.
    inputs:
      - name: task_instruction
        type: string
      - name: detected_layout
        type: object
      - name: layout_warnings
        type: list[*]
    questions:
      missing_value_policy:
        type: choice
        instructions: >
          How should blank Data cells (protein not quantified in a sample) enter the lookups and
          statistics? Values are log2, so 0 is a real measurement (ratio 1), not "missing".
          Choose zero only if the task statement explicitly says to treat missing or blank values
          as 0; silence on the subject means exclude.
        criteria:
          exclude: Blanks stay blank; means and stdevs use observed values only; a statistic with too few observations is left blank.
          zero: The task statement explicitly instructs that missing/blank values count as 0.
      layout_matches_task:
        type: noul
        instructions: >
          Do the detected cells agree with the task statement - lookup targets (rows x sample
          columns), group row with Control/Treated labels, the four statistics rows/columns and the
          fold-change columns with Fold Change and Log2 FC in the stated places - and did every
          protein and sample name resolve? Ignore the stale instruction text inside the sheet
          itself (it cites ranges like H7:BB16 and a Step 4 that do not exist); only the task
          statement and the yellow cells count. Blank-measurement warnings alone do not make the
          layout wrong.
        criteria:
          true: Every block matches the task statement's cells and there are no unresolved names or uncovered yellow target cells.
          false: Some block is missing, shifted, mis-ordered, or a protein/sample name did not resolve.
    thresholds:
      missing_value_policy: 0.6
      layout_matches_task: 0.2
    inputs_to: confirm-layout

  - name: confirm-layout
    kind: client_task
    description: Confirm the detected layout or write the minimal overrides that correct it.
    inputs:
      - name: task_instruction
        type: string
      - name: detected_layout
        type: object
      - name: layout_warnings
        type: list[*]
      - name: layout_matches_task
        type: boolean
    template: assets/confirm-layout.md
    references:
      - path: references/workbook-guide.md
        description: Block-by-block cell map, formulas, missing-value rationale, gotchas and the override format. Load when the layout does not match or a warning is unclear.
    outputs:
      - name: layout_overrides
        type: object
        description: Keys merged over detected_layout before filling; empty when the detection is correct.
    inputs_to: fill-workbook

  - name: fill-workbook
    kind: execution
    description: Write lookup, statistics and fold-change formulas into the target cells, save, recalculate with LibreOffice, and verify values, errors, yellow-cell coverage and styles.
    inputs:
      - name: workbook_path
        type: string
      - name: output_path
        type: string
      - name: detected_layout
        type: object
      - name: layout_overrides
        type: object
      - name: missing_value_policy
        type: string
    script: scripts/fill_workbook.py
    timeout: 400
    outputs:
      - name: verdict
        type: string
        description: verified when recalculated values match the independent check with zero formula errors, all yellow cells filled and styles unchanged; needs_attention otherwise.
      - name: fill_report
        type: object
        description: Cells written, example formulas, recalc result, blank-by-design cells, mismatches, style drift, and paths of the original backup and the formulas-only copy.
      - name: fill_issues
        type: list[*]
        description: Plain-language problems behind a needs_attention verdict; empty when verified.
    inputs_to: route-verdict

  - name: route-verdict
    kind: router
    description: A verified workbook is done; anything else goes to repair.
    branch_on: verdict
    branches:
      verified: end
      needs_attention: resolve-issues

  - name: resolve-issues
    kind: client_task
    description: Repair what the verification flagged, keeping formulas and formatting intact, and report the outcome.
    inputs:
      - name: fill_issues
        type: list[*]
      - name: fill_report
        type: object
      - name: output_path
        type: string
    template: assets/resolve-issues.md
    references:
      - path: references/workbook-guide.md
        description: Repair checklist, formulas per block, recalc usage and override format. Load for every repair.
    outputs:
      - name: resolution
        type: string
        description: What was fixed, how it was re-verified, and anything still unresolved.
    inputs_to: end

  - name: end
    kind: end
    description: The workbook at output_path holds formula-driven lookups, group statistics and fold changes; verdict records whether automatic verification passed.
    inputs:
      - name: output_path
        type: string
      - name: verdict
        type: string

anti_patterns:
  - Computing means or fold changes in Python and writing the numbers into cells; every target cell must be a formula that recalculates when Data changes.
  - Letting a bare INDEX/MATCH turn blank measurements into 0, which on a log2 scale is a real value and corrupts means and stdevs.
  - Following the stale instruction text inside the Task sheet (H7:BB16, H19:BB28, a Step 4) instead of the task statement and the yellow cells.
  - Filling the statistics block with proteins down the rows; it is transposed - one protein per column, four statistic rows.
  - Swapping the fold-change columns; Fold Change is the first yellow column and Log2 FC the second.
  - Computing fold change as a ratio of means; on log2 data Log2 FC = Treated Mean - Control Mean and FC = 2^Log2 FC.
  - Using population stdev (STDEVP/STDEV.P); group standard deviation is the sample stdev (STDEV).
  - Restyling cells, recolouring, changing number formats or fonts, or adding macros/VBA - the template's conventions win.
  - Opening the workbook with openpyxl data_only=True and saving it, which strips every formula.
  - Delivering formulas without recalculating, so a reader of cached values sees empty cells.
```
