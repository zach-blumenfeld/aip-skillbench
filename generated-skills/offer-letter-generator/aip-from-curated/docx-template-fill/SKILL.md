---
name: docx-template-fill
description: Fill a Word (.docx) template's {{KEY}} placeholders from a JSON data file with python-docx, e.g. generating an offer letter from offer_letter_template.docx + employee_data.json. Handles placeholders Word split across runs, headers/footers, nested tables, and {{IF_X}}...{{END_IF_X}} conditional sections (e.g. relocation), keeps run formatting, and verifies no placeholder or marker is left. Use for offer letters, contracts, mail-merge, or any docx template filling task.
compatibility: Python 3.8+ with python-docx 1.x (lxml comes with it).
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
  Produce a filled .docx from a Word template whose fields are {{KEY}} placeholders and
  whose optional sections are wrapped in {{IF_X}}...{{END_IF_X}}, using a flat JSON data
  file (offer letters are the typical case). Scripts do all document surgery: they find
  placeholders Word split across runs, cover the body, nested tables, every
  header/footer, text boxes and notes, decide each conditional block from its data flag,
  keep each run's formatting, save, and re-open the result to prove nothing is left.
  The agent steps in only to supply missing values, settle an undecidable condition, or
  repair what verification flags.

trigger_when:
  - A task asks to generate an offer letter (or contract, notice, mail-merge document) from a .docx template and a JSON/dict of field values.
  - A .docx contains {{PLACEHOLDER}} fields or {{IF_...}}/{{END_IF_...}} markers to fill or resolve.
  - A previous python-docx fill left placeholders behind, lost them in headers/footers or nested tables, or broke formatting.

do_not_use_when:
  - Building a Word document from scratch with no template.
  - The template uses Word merge fields (MERGEFIELD), content controls, or Jinja tags instead of {{KEY}} text; adapt with python-docx directly.
  - Converting .docx to PDF or another format.

steps:
  - name: inspect
    kind: execution
    description: Map every placeholder and conditional block in the template against the data; decide each condition; list missing values and path problems.
    inputs:
      - name: template_path
        type: string
        description: Absolute path to the .docx template (in the task container usually /root/offer_letter_template.docx).
      - name: data_path
        type: string
        description: Absolute path to the JSON object of KEY -> value (usually /root/employee_data.json). If the values arrive inline, write them to a JSON file first.
      - name: output_path
        type: string
        description: Absolute path for the filled .docx, exactly as the task names it. Never the template path.
    script: scripts/inspect_template.py
    inputs_to: route-inspect

  - name: route-inspect
    kind: router
    description: Clean inspection goes straight to the fill; any issue goes to the agent first.
    branch_on: inspect_status
    branches:
      ready: fill
      needs_input: resolve-inputs

  - name: resolve-inputs
    kind: client_task
    description: Supply missing values, settle undecided conditions, or fix the paths so the fill can run.
    inputs:
      - name: template_path
        type: string
      - name: output_path
        type: string
      - name: issues
        type: list[*]
        description: Blocking problems found by inspect.
      - name: notes
        type: list[*]
      - name: placeholders
        type: list[*]
      - name: values
        type: object
        description: KEY -> value to insert; starts as the data file.
      - name: conditions
        type: object
        description: IF_ name (without the prefix) -> true to keep the block, false to remove it.
      - name: condition_sources
        type: object
    template: assets/resolve-inputs.md
    inputs_to: fill

  - name: fill
    kind: execution
    description: Resolve conditional blocks, replace every placeholder in every part (keeping run formatting), and save to output_path.
    inputs:
      - name: template_path
        type: string
      - name: output_path
        type: string
      - name: values
        type: object
        description: KEY -> value. Inserted as text exactly as given; a value's leading currency symbol is dropped when the template already has one right before the placeholder.
      - name: conditions
        type: object
        description: Condition name -> include (true) / remove (false). Blocks with no entry are removed.
    script: scripts/fill_template.py
    inputs_to: verify-output

  - name: verify-output
    kind: execution
    description: Re-open the saved .docx and fail on any leftover braces, IF_/END_IF_ marker, or expected value missing from the text, across body, tables, headers and footers.
    inputs:
      - name: template_path
        type: string
      - name: output_path
        type: string
      - name: values
        type: object
      - name: conditions
        type: object
    script: scripts/verify_output.py
    inputs_to: route-verify

  - name: route-verify
    kind: router
    description: A verified document ends the run; a failed one goes to repair.
    branch_on: verify_status
    branches:
      verified: end
      failed: repair

  - name: repair
    kind: client_task
    description: Fix what verification flagged, by correcting values and re-filling or by editing the saved document directly.
    inputs:
      - name: template_path
        type: string
      - name: output_path
        type: string
      - name: values
        type: object
      - name: conditions
        type: object
      - name: problems
        type: list[*]
      - name: values_not_found
        type: list[*]
      - name: document_text
        type: string
    template: assets/repair.md
    references:
      - path: references/python-docx-patterns.md
        description: Paragraph-level replace, header/footer and nested-table traversal, and conditional-block code for python-docx. Load only when a fix needs hand-editing the .docx (placeholder or marker the scripts could not reach).
    inputs_to: verify-output

  - name: end
    kind: end
    description: The filled document on disk at output_path, verified free of placeholders and markers.
    inputs:
      - name: output_path
        type: string
      - name: verify_status
        type: string
      - name: values
        type: object
      - name: conditions
        type: object
      - name: document_text
        type: string
        description: Full text of the saved document, for the final answer.

anti_patterns:
  - Replacing inside run.text one run at a time; Word splits placeholders across runs ("{{CANDI" + "DATE_NAME}}"), so search paragraph text.
  - 'Walking only doc.paragraphs; headers/footers (e.g. "Document ID: {{DOC_ID}}", "Confidential - {{COMPANY_NAME}}") and nested tables (a table inside a table cell) are separate.'
  - Collapsing a whole paragraph into its first run; a bold/underlined placeholder after plain text (the response deadline) loses its formatting or plain text turns bold.
  - Leaving {{IF_RELOCATION}} / {{END_IF_RELOCATION}} markers in the output, or keeping a block whose flag (RELOCATION_PACKAGE) says "No".
  - Adding "$", "shares", "days" or reformatting numbers and dates; the template already carries that text and the data value goes in verbatim ("185,000" -> "$185,000 per year").
  - Deleting template text outside the IF_/END_IF_ markers (e.g. the "Relocation Assistance:" heading that precedes the block); only the marked span is conditional, so a removed block leaves its heading and an empty paragraph exactly as the template author laid it out.
  - Inventing a value for a missing placeholder, or overwriting the template instead of writing to the task's output path.
  - Declaring success without re-opening the saved file and checking every part for "{{" and markers.
```
