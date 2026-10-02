---
name: finance-doc-qa
description: Answer a numeric financial-analysis question over a paired Excel data file and background PDF. Extracts the background text, inspects the workbook, has the client derive the answer with Python (pandas + openpyxl + pypdf), then validates and writes the number to the requested output path. Use when a task hands you (1) a question, (2) a `.xlsx` data file, (3) a `.pdf` background document with the rules or definitions needed to interpret the data, and (4) an output file path expecting a single numeric answer. Keywords include financial modeling QA, spreadsheet analysis, PDF-grounded question answering, background rules, data.xlsx + background.pdf, answer.txt, pandas Excel, openpyxl, pypdf.
metadata:
  aip-version: "0.4a0"
---

# AIP runtime — format 0.4a0

You are executing an (Agent Instruction Protocol) AIP procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks using a graph-based workflow. AIP is portable, so while designed for execution with an AIP client and server, you, the agent can play both roles instead. 

## Running

If the `aip` command is available (`aip --help` succeeds), use it: run `aip run <this skill's folder> --input <start.json>` with the start step's inputs as JSON. When the run needs you it prints a JSON pause and exits with code 3. `paused` says why: `decision` — answer the listed questions; `review` — confirm or override the flagged answers; `client_task` — do the task and produce the keys in `expects`. Put your answer in a JSON file and run the `resume` command the pause printed. Repeat until the output has `"done": true`; `state` is the result. If `aip` is not available, execute the procedure yourself, following the semantics below.

Critical terminology:

- **Client**: whoever drives the run: posts each step's input, reviews uncertain decisions, performs client tasks, and makes the final call at every step. As a plain Agent Skill, it is the agent that activated the skill.
- **Server**: runs each step and validates its input against the step's `inputs`. Without one, the activating agent does this itself: runs scripts, answers decision questions by its own judgment, and follows routers.
- **State**: the JSON object a step receives. Each step declares its required keys as `inputs`; extra keys pass through.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to the client, `router` branches on a value in the state, `end` declares the final state's shape.

## Execution

The state is one JSON object. It starts as the start step's `inputs` and flows along `inputs_to`; each step's output is merged over it, so keys accumulate and extra keys pass through untouched. A step runs only if the state holds every key it declares in `inputs`, with the declared types. The client may change the state before any step runs; it has the final say at every step.

- **`execution`**: run `script` with one JSON object on stdin, `{"currentState": <state>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout; it is merged over the state.
- **`decision`**: answer each question against the state. Each answer collapses to one value under its question name and is merged over the state: a noul to `true`/`false`, a choice to its label, a score to its level number. With a decision model, an answer under its threshold is sent to the client to confirm or override before continuing; without one, the client answers the questions.
- **`client_task`**: render `template` with `{key}` from the state, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. The client performs the task, loading `references` if their descriptions apply, and returns the next step's `inputs`; they are merged over the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. That state is the procedure's result.

```yaml
purpose: >
  Answer a numeric question about a spreadsheet whose interpretation depends on a
  background PDF. Extract the PDF text, summarize the workbook structure, hand the
  question + rules + data structure to the client to compute the number in Python,
  then validate the format and write it to the requested output path.

trigger_when:
  - The task hands you a question, a data.xlsx, a background.pdf, and an answer output path expecting a single number.
  - A financial-analysis prompt names a spreadsheet plus a rules or context document and asks for one numeric result.

do_not_use_when:
  - The task requires creating or editing an Excel model (formulas, formatting, color coding). This skill only reads workbooks.
  - The task requires filling out or generating a PDF form.
  - The answer must be prose, a table, a chart, or multiple values.

steps:
  - name: extract-background
    kind: execution
    description: Extract text from the background PDF with pypdf.
    inputs:
      - name: question
        type: string
        description: The natural-language question to answer.
      - name: data_path
        type: string
        description: Absolute path to the .xlsx data file (typically /root/data.xlsx).
      - name: background_path
        type: string
        description: Absolute path to the background .pdf (typically /root/background.pdf).
      - name: answer_path
        type: string
        description: Absolute path to write the final numeric answer to (typically /root/answer.txt).
    script: scripts/extract_background.py
    inputs_to: inspect-data

  - name: inspect-data
    kind: execution
    description: Enumerate sheets and produce a shape + dtype + head preview per sheet.
    inputs:
      - name: data_path
        type: string
    script: scripts/inspect_data.py
    inputs_to: answer-question

  - name: answer-question
    kind: client_task
    description: Combine the question, extracted background rules, and data summary; write and run a Python script that produces the numeric answer.
    inputs:
      - name: question
        type: string
      - name: background_text
        type: string
      - name: data_summary
        type: string
      - name: data_path
        type: string
    template: assets/analysis_template.md
    references:
      - path: references/pandas-openpyxl-patterns.md
        description: Load when the workbook's columns, header rows, or grouping structure is ambiguous — covers raw-load-and-coerce, content-based column detection, deterministic grouping, and known-good row insertion.
      - path: references/pypdf-patterns.md
        description: Load when the background text extracted into state looks garbled, incomplete, or you need per-page access. Covers pypdf's limits and the container's frozen library set.
    inputs_to: write-answer

  - name: write-answer
    kind: execution
    description: Validate the answer matches `^-?\d+(\.\d+)?$` and write it to answer_path.
    inputs:
      - name: answer
        type: string
      - name: answer_path
        type: string
    script: scripts/write_answer.py
    inputs_to: end

  - name: end
    kind: end
    description: The final numeric answer is written to answer_path.
    inputs:
      - name: answer_written
        type: string
      - name: answer_path
        type: string

anti_patterns:
  - Answering from the question and background alone without opening the .xlsx — the data almost always changes the number.
  - Hardcoding sheet or column indices without inspecting the workbook first.
  - Ignoring a "missing row" or "example row" that the background PDF calls out; it must be present before scoring.
  - Writing text, units, commas, or a percent sign into answer.txt — the writer rejects anything that is not a bare number.
  - Installing extra Python packages at runtime; the container ships pandas 2.2.3, openpyxl 3.1.5, and pypdf 5.1.0 and nothing else pdf/xlsx-related.
  - Using openpyxl with `data_only=True` to read cached formula values without checking whether the workbook was ever calculated (uncomputed cells return None).
```
