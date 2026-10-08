---
name: case-study-model-qa
description: Answer financial-modeling case-study questions (ModelOff style) from a background PDF of rules plus an Excel data workbook. Reads the PDF, profiles the workbook for layout traps (displaced records, blank rows, text numbers), builds the model in Python over every record, and picks or types the answer. Includes a dedicated scorer for the dice-scoring case ("Roll The Dice"; High and Often, Summation, Highs and Lows, Only two numbers, All the numbers, Ordered subset of four; best game score with no category repeated). Falls back to guided pandas/openpyxl modelling for other cases, with spreadsheet-deliverable rules (live formulas, zero errors, colour and number formats).
license: Proprietary. Compiled from Anthropic pdf and xlsx skills; see source/pdf/LICENSE.txt and source/xlsx/LICENSE.txt
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
  Turn a case-study pack (background.pdf rules + data.xlsx) and a question into a
  checked answer. Scripts extract the PDF text and profile every sheet, so that hidden
  layout traps show up before any modelling. A decision identifies the case. For the
  dice-scoring case, the agent confirms the rule table against the PDF, and a
  script scores all turns and games, recovering displaced records and writing
  per-turn and per-game CSVs. The agent then answers from that summary at the
  precision the question needs. Other cases get a guided modelling task that applies
  the same loading discipline and the spreadsheet conventions.

trigger_when:
  - A task gives a case-study or information-pack PDF and an Excel workbook and asks questions to answer from a model.
  - ModelOff or financial-modeling-competition style questions (multiple choice or typed number) about simulated data.
  - Questions about dice rolls, turns, games, scoring categories, or the highest possible game score.
  - The user asks to build a spreadsheet model from a rules document and report results from it.

do_not_use_when:
  - Only filling in a PDF form, or merging, splitting, or watermarking PDFs. No modelling question is involved.
  - Formatting or editing a spreadsheet without answering a question from data.

steps:
  - name: read-inputs
    kind: execution
    description: Extract the PDF text and profile every workbook sheet (header rows, numeric blocks, blank rows inside blocks, numbers outside the main block, text-stored numbers, formula count). Optional start key work_dir sets where score-dice writes turns.csv and games.csv (default <tmp>/dice_model).
    inputs:
      - name: question
        type: string
        description: The question(s) to answer, verbatim, including any multiple-choice options.
      - name: pdf_path
        type: string
        description: Absolute path to the case-study PDF (e.g. /root/background.pdf).
      - name: xlsx_path
        type: string
        description: Absolute path to the data workbook (e.g. /root/data.xlsx).
    script: scripts/extract_inputs.py
    timeout: 120
    inputs_to: classify-case

  - name: classify-case
    kind: decision
    description: Decide which case this is and what form the answer must take.
    inputs:
      - name: question
        type: string
      - name: pdf_text
        type: string
        description: Full text of the case-study PDF.
      - name: workbook_profile
        type: object
        description: Per-sheet layout profile from read-inputs.
    questions:
      case_type:
        type: choice
        instructions: >
          Which case does the PDF describe? Judge by its rules, not by the title.
          Dice scoring means turns of die rolls scored in categories such as
          High and Often, Summation, Highs and Lows, Only two numbers, All the
          numbers, and Ordered subset of four, with games combining turns.
        criteria:
          dice_scoring: A dice game whose turns of rolls are scored by category rules and whose games combine turns with categories not reused. The data is a list of turns with roll columns.
          other: Any other case (financial projections, loans, depreciation, a different game or simulation), or dice rules that do not fit those categories.
      answer_format:
        type: choice
        instructions: What form does the question require for the answer?
        criteria:
          multiple_choice: The question lists options to choose from.
          number: A typed numeric answer with no options.
          workbook: The deliverable is a built or edited spreadsheet file, possibly with numbers reported too.
          text: A short explanation or label, with no number to compute.
    thresholds:
      case_type: 0.8
    inputs_to: route-case

  - name: route-case
    kind: router
    description: The dice-scoring case uses the dedicated scorer; anything else is modelled by the agent.
    branch_on: case_type
    branches:
      dice_scoring: confirm-dice-rules
      other: model-generic

  - name: confirm-dice-rules
    kind: client_task
    description: Check the default scoring rules against the PDF table and the question; output the rules object the scorer uses.
    inputs:
      - name: question
        type: string
      - name: pdf_text
        type: string
      - name: workbook_profile
        type: object
    template: assets/confirm_rules.md
    assets:
      - assets/dice_rules.json
    references:
      - path: references/pdf-guide.md
        description: Fallbacks for when the PDF text is empty, garbled, or the scoring table is mangled.
    inputs_to: score-dice

  - name: score-dice
    kind: execution
    description: Load every turn, recovering displaced records and reporting anomalies. Score each turn in every category and each game as its best total with distinct categories. Write turns.csv and games.csv and return summary statistics.
    inputs:
      - name: xlsx_path
        type: string
      - name: dice_rules
        type: object
        description: Rules object shaped like assets/dice_rules.json, as confirmed in the previous step.
    script: scripts/score_dice.py
    timeout: 300
    inputs_to: answer-dice-question

  - name: answer-dice-question
    kind: client_task
    description: Answer the question from the scoring summary, querying the CSVs with pandas for anything the summary lacks.
    inputs:
      - name: question
        type: string
      - name: answer_format
        type: string
      - name: dice_summary
        type: object
        description: Per-category turn stats, best-turn stats, game-score stats and distributions, and category usage in optimal games.
      - name: data_issues
        type: list[*]
        description: Every loading anomaly found and how it was handled.
      - name: turns_csv
        type: string
      - name: games_csv
        type: string
    template: assets/answer_dice.md
    references:
      - path: references/dice-case.md
        description: Case structure, workbook traps, and a question-reading checklist (denominators, ties, "above" vs "at least"). Load when the wording is ambiguous or no option matches.
      - path: references/xlsx-guide.md
        description: Spreadsheet rules. Load only if the task also asks for a workbook deliverable.
    inputs_to: end

  - name: model-generic
    kind: client_task
    description: Model a non-dice case yourself from the PDF rules and the profiled workbook, then answer.
    inputs:
      - name: question
        type: string
      - name: answer_format
        type: string
      - name: pdf_text
        type: string
      - name: workbook_profile
        type: object
      - name: xlsx_path
        type: string
    template: assets/generic_model.md
    references:
      - path: references/xlsx-guide.md
        description: pandas and openpyxl reading tips, plus deliverable-workbook rules (formulas not hardcodes, zero errors, colour codes, number formats, recalc.py, and what to do without LibreOffice).
      - path: references/pdf-guide.md
        description: PDF text and table extraction fallbacks with the container's pypdf, plus OCR or pdftotext when they are available.
    inputs_to: end

  - name: end
    kind: end
    description: The answer and a short account of how it was computed.
    inputs:
      - name: answer
        type: string
        description: Final answer in the form the question requires (the option, or the number).
      - name: working
        type: string
        description: What was computed, from which data, with which denominator, and which data issues mattered.

anti_patterns:
  - Reading the data with a plain pd.read_excel + dropna and missing records moved outside the table. The case packs plant displaced rows, so always check data_issues or the profile's numeric_cells_outside_main_block.
  - Scoring a game as the sum of each turn's best category when both turns pick the same category. Categories cannot repeat within a game.
  - Counting non-adjacent or sorted rolls as an "ordered subset of four", or counting a single repeated value as "only two numbers".
  - Averaging a fixed-point category only over the turns that score it when the question means all turns (or the reverse) without saying which.
  - Picking the closest multiple-choice option without first rechecking the rules and data issues when nothing matches exactly.
  - Hardcoding Python-computed numbers into a deliverable workbook instead of live formulas, or delivering a workbook with formula errors.
  - Assuming pdfplumber, LibreOffice, or other packages beyond pandas, openpyxl, and pypdf exist in the task container.
```
