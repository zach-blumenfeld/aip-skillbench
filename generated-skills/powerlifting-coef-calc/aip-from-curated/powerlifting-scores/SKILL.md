---
name: powerlifting-scores
description: Compute powerlifting points (Dots, Wilks, IPF GL / Goodlift, Glossbrenner) for lifters in an Excel workbook such as an OpenPowerlifting/OpenIPF export, writing a scoring sheet of live Excel formulas (copied lifter columns, TotalKg, score) that is recalculated with LibreOffice and verified cell by cell against the OpenPowerlifting reference formulas. Use when asked to calculate Dots, Wilks, IPF GL or Glossbrenner coefficients or points, normalize lifts by bodyweight, or fill a scores sheet in an .xlsx of meet results.
metadata:
  aip-version: "0.5a1"
  version: "1.0"
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
  Fill a scoring sheet in a powerlifting results workbook (OpenPowerlifting-style columns:
  Name, Sex, Event, Equipment, BodyweightKg, Best3SquatKg/BenchKg/DeadliftKg, optional TotalKg)
  with Dots, Wilks, IPF GL, or Glossbrenner points. Scripts carry the exact OpenPowerlifting
  constants, bodyweight clamps, sex and equipment mappings and zero rules, emit them as live
  Excel formulas (never pasted numbers), recalculate with LibreOffice, and check every cell
  against a Python reference validated on the published test vectors. The agent only maps the
  task's wording to a layout plan.

trigger_when:
  - A task asks to calculate Dots, Wilks, IPF GL / Goodlift, or Glossbrenner coefficients or points.
  - An .xlsx of meet results (e.g. openipf.xlsx with Data and Dots sheets) needs a scores sheet filled with formulas.
  - Someone wants lifters compared across bodyweights or sexes with a standard powerlifting formula.

do_not_use_when:
  - The task is training programming, attempt selection, or meet-day coaching with no score calculation.
  - The data is not a spreadsheet and no workbook output is wanted (compute with scripts/pl_lib.py points() directly instead).
  - The request is general spreadsheet work unrelated to lifter scoring.

steps:
  - name: profile-workbook
    kind: execution
    description: Read the workbook; report sheets, headers, row counts, Sex/Event/Equipment values, bodyweight range, data anomalies, and a header-matched draft plan.
    inputs:
      - name: workbook_path
        type: string
        description: Absolute path to the .xlsx to score (in the task container usually /root/data/openipf.xlsx).
      - name: task_request
        type: string
        description: The task text verbatim, including any sheet names, column lists, rounding, and output path it specifies.
    script: scripts/profile_workbook.py
    timeout: 120
    inputs_to: classify-request

  - name: classify-request
    kind: decision
    description: Decide which scoring system the task asks for.
    inputs:
      - name: task_request
        type: string
      - name: profile
        type: object
        description: Workbook profile; sheet names (e.g. a sheet called Dots) hint at the system.
    questions:
      score_system:
        type: choice
        instructions: >
          Which powerlifting score must be computed? Use the task text first; an empty target
          sheet named after a system (profile.system_hint_from_sheet_name) confirms it. "DOTS",
          "Dynamic Objective Team Scoring" mean dots. "IPF points", "GL", "Goodlift", "IPF GL
          coefficient" mean ipf_gl. "Coefficient" alone next to one of these names means that
          system; whether points or the bare coefficient are written is settled in the plan.
        criteria:
          dots: Dots score/coefficient.
          wilks: Wilks score/coefficient (original Wilks, not Wilks2 / Wilks-2020).
          ipf_gl: IPF GL / Goodlift points (2020 coefficients).
          glossbrenner: Glossbrenner points (GPC style).
          multiple: Two or more of the above in the same sheet.
          other: Any other formula (Wilks2, old IPF points, McCulloch, Reshel, age-adjusted masters scores, Sinclair).
    thresholds:
      score_system: 0.7
    inputs_to: route-system

  - name: route-system
    kind: router
    description: Scripted systems go to the layout plan; anything else is done by hand.
    branch_on: score_system
    branches:
      dots: plan-layout
      wilks: plan-layout
      ipf_gl: plan-layout
      glossbrenner: plan-layout
      multiple: plan-layout
      other: manual-score

  - name: plan-layout
    kind: client_task
    description: Turn the task's wording into the write_scores plan (sheets, ordered columns, total policy, rounding, output path).
    inputs:
      - name: task_request
        type: string
      - name: score_system
        type: string
      - name: profile
        type: object
      - name: draft_plan
        type: object
    template: assets/plan_layout.md
    references:
      - path: references/openpowerlifting-data.md
        description: Meaning of each OpenPowerlifting column (Mx, negative lifts, empty TotalKg, Place codes, WeightClassKg text). Load when the profile shows anomalies or unfamiliar values.
      - path: references/scoring-formulas.md
        description: Constants, clamps, sex/equipment/event mappings and test values for Dots, Wilks, IPF GL, Glossbrenner. Load when the task describes a variant or asks for a coefficient rather than points.
    inputs_to: write-scores

  - name: write-scores
    kind: execution
    description: Write the target sheet as Excel formulas, cache reference values, recalculate with LibreOffice, and verify every cell, header, and the untouched data sheet.
    inputs:
      - name: workbook_path
        type: string
      - name: plan
        type: object
        description: Layout plan from plan-layout or repair-plan.
      - name: score_system
        type: string
    script: scripts/write_scores.py
    timeout: 300
    inputs_to: check-verification

  - name: check-verification
    kind: router
    description: Verified output goes to the final check; failures go to repair.
    branch_on: verify_status
    branches:
      pass: final-check
      pass_cached: final-check
      fail: repair-plan

  - name: repair-plan
    kind: client_task
    description: Diagnose the verification failure and emit a corrected plan, or stop after a repeated failure.
    inputs:
      - name: task_request
        type: string
      - name: plan
        type: object
      - name: verification
        type: object
      - name: profile
        type: object
    template: assets/repair_plan.md
    references:
      - path: references/xlsx-rules.md
        description: Formula-error causes and openpyxl pitfalls (data_only saves, 1-based indices, cross-sheet quoting). Load when the failure is a formula error or a lost formula.
    inputs_to: retry-or-stop

  - name: retry-or-stop
    kind: router
    description: Rerun the writer with the repaired plan, or stop and report.
    branch_on: repair_action
    branches:
      retry: write-scores
      stop: final-check

  - name: manual-score
    kind: client_task
    description: Build a sheet for a scoring formula the pack does not script, by hand with openpyxl formulas and recalc.py.
    inputs:
      - name: task_request
        type: string
      - name: profile
        type: object
      - name: workbook_path
        type: string
    template: assets/manual_score.md
    references:
      - path: references/xlsx-rules.md
        description: Output requirements (zero formula errors, formulas not values, preserve the template), openpyxl and recalc.py usage. Load before editing the workbook.
      - path: references/openpowerlifting-data.md
        description: Column semantics for OpenPowerlifting data. Load when mapping columns to the formula's inputs.
    inputs_to: final-check

  - name: final-check
    kind: client_task
    description: Confirm the written workbook satisfies the task text exactly and summarise it.
    inputs:
      - name: task_request
        type: string
      - name: output_path
        type: string
      - name: verify_status
        type: string
      - name: verification
        type: object
    template: assets/final_check.md
    inputs_to: end

  - name: end
    kind: end
    description: The scored workbook on disk plus the verification outcome and a short summary.
    inputs:
      - name: output_path
        type: string
      - name: verify_status
        type: string
      - name: summary
        type: string

anti_patterns:
  - Computing scores in Python and pasting numbers into cells; the sheet must hold formulas that recalculate when Data changes.
  - Opening the workbook with data_only=True and saving it, which destroys every formula.
  - Renaming, reordering or adding columns, sheets, notes or colour coding beyond what the task asks; graders read the exact layout.
  - Using WeightClassKg (text like "84+") instead of BodyweightKg, or treating Mx as women.
  - Applying Dots or Wilks constants without the bodyweight clamps (Dots men 40-210, women 40-150; Wilks men 40-201.9, women 26.51-154.53).
  - Summing a negative Best3 value (a failed attempt) into a total; OpenPowerlifting gives that lifter no total and 0 points.
  - Rounding when the task did not ask for it, or rounding in Python instead of with Excel ROUND().
  - Writing the test or scratch files inside the skill folder or modifying the Data sheet.
```
