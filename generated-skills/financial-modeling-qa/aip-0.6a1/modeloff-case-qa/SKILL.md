---
name: modeloff-case-qa
description: Answer a financial-modelling case question (ModelOff-style) from an Excel data workbook (.xlsx) plus a PDF case background, writing only the final value to an answer file. Profiles every sheet, extracts the PDF rules, recovers displaced or blank rows, and fully scores the "Roll The Dice" case (turn categories High and Often, Summation, Highs and Lows, Only two numbers, All the numbers, Ordered subset of four; best two-turn game score; odd-vs-even player matches). Use for data.xlsx + background.pdf analysis questions, dice-game scoring, simulated games, and other spreadsheet case-study questions.
license: Proprietary. source/xlsx/LICENSE.txt and source/pdf/references/LICENSE.txt have complete terms
metadata:
  aip-version: "0.6a1"
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
  Answer one analysis question about a financial-modelling case whose data is an Excel
  workbook and whose rules are in a PDF background, and write only the answer to a file.
  A script extracts the PDF text and profiles the workbook (header rows, samples, layout
  anomalies); a decision recognises the case. The Roll The Dice case is scored completely
  by a script (every turn category, best game score with distinct categories, standard
  aggregates, odd-vs-even matches) after rebuilding the turn table from records that may
  have been displaced; any other case is modelled by the agent in pandas. A script
  normalises and writes the answer.

trigger_when:
  - A task gives an .xlsx data file and a PDF background and asks a numeric or multiple-choice financial or data-analysis question.
  - A question concerns the ModelOff "Roll The Dice" case (dice turns, games, categories, players, matches).
  - The answer must be written to a text file as a bare value.

do_not_use_when:
  - The task asks to build, format, or deliver an Excel model rather than answer a question from data.
  - The task is filling, merging, or creating PDF files.

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - pandas>=2.0
    - openpyxl>=3.1
    - pypdf>=4.0

steps:
  - name: inspect-inputs
    kind: execution
    description: >
      Extract the PDF background text page by page (pypdf) and profile every workbook sheet:
      size, formula count, title rows, detected header row with column letters, first and last
      data rows, and NOTE lines for values lying outside the header columns.
    inputs:
      - name: question
        type: string
        description: The question exactly as given in the task statement, including any answer-format note.
      - name: data_path
        type: string
        description: Absolute path to the data workbook, e.g. /root/data.xlsx.
      - name: background_path
        type: string
        description: Absolute path to the case background PDF, e.g. /root/background.pdf.
      - name: answer_path
        type: string
        description: Absolute path the answer must be written to, e.g. /root/answer.txt.
      - name: work_dir
        type: string
        description: Writable scratch folder for intermediate tables, outside the skill folder, e.g. /root/work.
    script: scripts/inspect_inputs.py
    outputs:
      - name: background_text
        type: string
        description: Text of the background PDF, pages marked, truncated at 30000 characters.
      - name: workbook_summary
        type: string
        description: Per-sheet profile with header row, column letters, sample rows, and layout anomaly notes.
    inputs_to: classify-case

  - name: classify-case
    kind: decision
    description: Recognise which case the files describe and what form the answer takes.
    inputs:
      - name: question
        type: string
      - name: background_text
        type: string
      - name: workbook_summary
        type: string
    questions:
      case_type:
        type: choice
        instructions: >
          Which case do the background and workbook describe? Dice means the rules match the
          Roll The Dice game (2 turns per game, six rolls of one die per turn, scoring categories
          such as High and Often / Summation / Highs and Lows / Only two numbers / All the numbers /
          Ordered subset of four, best combined score with no category used twice) AND the workbook
          has a turn table with Turn number, Game number, Roll 1..Roll 6.
        criteria:
          dice: Roll The Dice rules and a turn table with Turn number, Game number, Roll 1 to Roll 6.
          other: Any other case, or dice rules that differ materially from those categories, or a different table layout.
      answer_format:
        type: choice
        instructions: >
          What form must the written answer take, judged from the question and its notes? A count,
          difference of counts, or whole-number score is integer.
        criteria:
          integer: A whole number (counts, differences of counts, integer scores, years).
          decimal: A number that may have a fractional part (averages, ratios, money, percentages).
          text: A label, option letter, name, or anything not a single number.
    thresholds:
      case_type: 0.3
      answer_format: 0.3
    inputs_to: by-case

  - name: by-case
    kind: router
    description: The dice case has a complete scoring script; anything else is modelled by the agent.
    branch_on: case_type
    branches:
      dice: score-dice
      other: general-model

  - name: score-dice
    kind: execution
    description: >
      Rebuild the turn table from every 8-cell turn record in any sheet (recovering records cut and
      pasted outside the table, blank rows, text numbers, duplicates) keyed by turn number; score each
      turn in all six categories (fixed scores parsed from the background, defaults 30/40/50); score
      each game as the best sum of the two turns in two different categories; write dice_turns.csv and
      dice_games.csv to work_dir; precompute category totals/means/max/qualifying counts, game score
      distribution, ties in the optimal assignment, and odd-vs-even player matches (game 2k-1 vs 2k,
      higher game score wins, equal is a tie for neither).
    inputs:
      - name: data_path
        type: string
      - name: background_text
        type: string
      - name: work_dir
        type: string
    script: scripts/dice_model.py
    outputs:
      - name: dice_turns_csv
        type: string
        description: Absolute path of the per-turn table (rolls plus all six category scores).
      - name: dice_games_csv
        type: string
        description: Absolute path of the per-game table (best score, chosen and all optimal category pairs).
      - name: dice_stats
        type: object
        description: Standard aggregates, fixed scores used and their source, and odd-vs-even match results.
      - name: dice_data_issues
        type: list[*]
        description: Every layout or data repair made while loading (displaced records, text numbers, missing turns).
    inputs_to: answer-dice

  - name: answer-dice
    kind: client_task
    description: Answer the question from the precomputed dice stats, or by a pandas query over the two CSVs.
    inputs:
      - name: question
        type: string
      - name: dice_stats
        type: object
      - name: dice_data_issues
        type: list[*]
      - name: dice_turns_csv
        type: string
      - name: dice_games_csv
        type: string
    template: assets/dice_answer.md
    references:
      - path: references/dice-case-rules.md
        description: Rule table, interpretations (adjacent runs, exactly two distinct values, ties), data traps, CSV columns, and which stat answers which question pattern. Always load on this branch.
    outputs:
      - name: dice_answer
        type: string
        description: Only the final value, written as the question asks.
    inputs_to: write-dice-answer

  - name: write-dice-answer
    kind: execution
    description: Normalise the dice answer to the decided format (strip separators and units, parentheses to minus, reject a fractional integer) and write it to answer_path.
    inputs:
      - name: dice_answer
        type: string
      - name: answer_path
        type: string
      - name: answer_format
        type: string
    script: scripts/write_answer.py
    outputs:
      - name: dice_answer_written
        type: string
        description: The exact text written to the answer file.
    inputs_to: end

  - name: general-model
    kind: client_task
    description: Model a non-dice case in pandas from the background rules and the workbook profile, and compute the answer.
    inputs:
      - name: question
        type: string
      - name: data_path
        type: string
      - name: workbook_summary
        type: string
      - name: background_text
        type: string
    template: assets/model_answer.md
    references:
      - path: references/xlsx-analysis.md
        description: Container limits, pandas/openpyxl loading with offset headers, data pitfalls (displaced rows, NaN, text numbers, off-by-one), and the modelling checklist. Always load on this branch.
      - path: references/pdf-reference.md
        description: Advanced PDF extraction (pypdfium2, pdfplumber coordinates, OCR fallback). Only if the background text is empty, garbled, or a table in it must be read by position.
    outputs:
      - name: model_answer
        type: string
        description: Only the final value, written as the question asks.
    inputs_to: write-model-answer

  - name: write-model-answer
    kind: execution
    description: Normalise the modelled answer to the decided format and write it to answer_path.
    inputs:
      - name: model_answer
        type: string
      - name: answer_path
        type: string
      - name: answer_format
        type: string
    script: scripts/write_answer.py
    outputs:
      - name: model_answer_written
        type: string
        description: The exact text written to the answer file.
    inputs_to: end

  - name: end
    kind: end
    description: The question and the answer file path; the file holds only the answer.
    inputs:
      - name: question
        type: string
      - name: answer_path
        type: string

anti_patterns:
  - Reading the turn table with dropna or only the header columns, losing a displaced record and shifting every pairing after it.
  - Pairing games or matches by row position instead of the Game number column.
  - Letting two turns of one game use the same category, or counting a non-qualifying fixed category at its fixed score.
  - Counting a tied match as a win for either player.
  - Writing units, words, or explanations into the answer file when the task asks for only the number.
  - Hardcoding an answer instead of computing it from the files given.
  - Assuming LibreOffice, pdfplumber, or poppler tools exist in the container; only pandas, openpyxl, and pypdf do.
```
