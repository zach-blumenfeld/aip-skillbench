---
name: financial-model-qa
description: Answer a question about a financial model distributed as an Excel workbook plus a background PDF. Extracts every non-empty cell (value + formula + number format + comment) and the per-page PDF plaintext, then the agent reasons over both to produce a grounded, cell/page-cited answer with unit and sign fidelity. Use when a prompt names an .xlsx model and a .pdf memo/background and asks for a figure, metric (IRR, NPV, margin, growth), assumption source, or narrative claim grounded in the model.
compatibility: Python 3 with openpyxl and pypdf installed (both ship in the task container's Dockerfile).
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
  Answer a question about a financial model packaged as an Excel workbook plus a background
  PDF. A script extracts every non-empty cell (cached value, formula, number format, comment)
  and the per-page PDF plaintext; the agent then reasons over both and returns a direct
  answer with a short justification that cites sheet-and-cell or page references.

trigger_when:
  - A prompt names an .xlsx workbook and a background .pdf and asks a question grounded in the model.
  - A reviewer asks for a figure, metric (IRR, NPV, margin, growth, multiple), assumption source,
    or narrative claim that the model and memo together should answer.

do_not_use_when:
  - The task is to build or edit a workbook, fill a PDF form, or merge/split PDFs — this skill reads only.
  - The question needs data neither file carries (e.g. a market quote from a terminal).
  - OCR is required because the PDF is scanned image-only; `pypdf` cannot extract text from scans.

steps:
  - name: extract
    kind: execution
    description: Load every sheet of the workbook (values + formulas + number formats + comments) and the full PDF plaintext per page, emit one JSON blob the client reasons over.
    inputs:
      - name: question
        type: string
        description: The user's question about the model, verbatim.
      - name: xlsx_path
        type: string
        description: Absolute or relative path to the .xlsx workbook.
      - name: pdf_path
        type: string
        description: Absolute or relative path to the background .pdf.
    script: scripts/extract_sources.py
    inputs_to: answer

  - name: answer
    kind: client_task
    description: Read the extracted workbook and PDF text, resolve the question against them, and produce one grounded answer with a short justification citing cells and page numbers.
    inputs:
      - name: question
        type: string
      - name: xlsx_data
        type: object
        description: Output of extract_sources.py — sheets, cells, named ranges, extractor notes.
      - name: pdf_text
        type: string
        description: Per-page plaintext of the background PDF, pages delimited by "=== Page N ===".
    template: assets/answer_prompt.md
    references:
      - path: references/xlsx-reading.md
        description: Load when a question needs structure the first-pass extract didn't carry — pandas tabular scans, cross-sheet reference traversal beyond named ranges, font-color/fill introspection, or column-letter arithmetic.
      - path: references/pdf-reading.md
        description: Load when the per-page plaintext is garbled, when the question needs table rows and columns, or when PDF metadata (title/author/subject) matters.
      - path: references/financial-conventions.md
        description: Load when the question hinges on units, color-coded cell meanings, formula construction conventions, source citations for hardcoded inputs, or how to interpret Excel error values.
    inputs_to: end

  - name: end
    kind: end
    description: The original question plus the grounded answer and its justification.
    inputs:
      - name: question
        type: string
      - name: answer
        type: string
        description: One-line direct answer when possible; preserves units and sign conventions from the model.
      - name: justification
        type: string
        description: 2–6 bullet points citing sheet-and-cell refs or PDF page numbers; names gaps when the model lacks the needed input instead of guessing.

anti_patterns:
  - Answering from the PDF prose when the workbook holds a cell with the exact figure, or vice versa — always cross-check the authoritative source.
  - Reporting a cached value without checking whether it is `null` (workbook never recalculated) — recompute from the formula chain instead.
  - Dropping the unit label (`$mm`, `%`, `x`) because the raw cell value looks like a plain number.
  - Guessing a figure when the needed cell is blank or a referenced sheet is missing — say what's missing instead.
  - Flipping sign conventions on costs modeled as positive numbers but subtracted downstream.
```
