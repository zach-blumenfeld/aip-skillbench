---
name: offer-letter-filler
description: Fill a Word (.docx) offer-letter or other document template whose {{PLACEHOLDER}} fields come from a JSON data file, using python-docx. Handles placeholders split across runs, nested tables, headers/footers, and conditional sections {{IF_X}}...{{END_IF_X}} kept or removed by a Yes/No data flag (e.g. RELOCATION_PACKAGE), then verifies no template markup remains. Use for offer letters, contracts, mail-merge style docx generation.
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
  Produce a finished Word offer letter (or any .docx template) by filling every
  {{KEY}} placeholder from a JSON data file and resolving {{IF_X}}...{{END_IF_X}}
  conditional sections from the matching Yes/No data flag. A script does the fill
  robustly (split runs, nested tables, headers/footers, formatting kept, no leftover
  markers) and reports issues; a review decision gates the result; the agent repairs
  only when something is unresolved.

trigger_when:
  - A task asks to fill a Word/.docx template that uses {{PLACEHOLDER}} fields from a JSON (or similar) data file.
  - Generating an offer letter, contract, or other mail-merge style document from employee or customer data.
  - A .docx template has conditional blocks like {{IF_RELOCATION}}...{{END_IF_RELOCATION}} that must be kept or removed by a data flag.

do_not_use_when:
  - The template is not a .docx (Google Docs, PDF forms, plain text) — use a tool for that format.
  - The task is to design or rewrite the letter's wording rather than fill a given template.

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - python-docx

steps:
  - name: fill-template
    kind: execution
    description: >
      Fill the template from the data and save the .docx. Conditionals {{IF_X}} follow the
      data flag for X (X, X_PACKAGE, INCLUDE_X, HAS_X, ...): yes-like keeps the content and
      strips only the markers, no-like removes markers and content (whole paragraphs when
      emptied). Placeholders are matched at paragraph level so split runs are found, in the
      body, nested tables, text boxes, headers and footers; only the placeholder characters
      are rewritten so surrounding formatting survives; a value's leading currency sign is
      dropped when the template already writes one ("${{BASE_SALARY}}"). Re-opens the saved
      file and reports any leftover markup.
    inputs:
      - name: template_path
        type: string
        description: The .docx template, e.g. /root/offer_letter_template.docx.
      - name: data_path
        type: string
        description: JSON file of placeholder values (flat object; nested objects and single-record lists are flattened), e.g. /root/employee_data.json.
      - name: output_path
        type: string
        description: Where to save the filled .docx, exactly as the task states, e.g. /root/offer_letter_filled.docx.
    script: scripts/fill_template.py
    outputs:
      - name: output_file
        type: string
        description: Path of the saved filled document.
      - name: filled_placeholders
        type: object
        description: Placeholder name to the text written in its place.
      - name: conditionals
        type: object
        description: Per IF_X block, the data key used, its value, and whether the block was included (null when unresolved).
      - name: issues
        type: list[*]
        description: Problems found (missing data values, unclear flags, unmatched markers, leftover markup); empty when clean.
      - name: letter_text
        type: string
        description: Plain text of the saved document, body first, then [hdr]/[ftr] lines.
      - name: status
        type: string
        description: complete when issues is empty, needs_attention otherwise.
    inputs_to: review-letter

  - name: review-letter
    kind: decision
    description: Judge whether the saved letter is a finished document ready to hand over.
    inputs:
      - name: letter_text
        type: string
      - name: issues
        type: list[*]
      - name: conditionals
        type: object
      - name: status
        type: string
    questions:
      ready:
        type: noul
        instructions: >
          Is the filled letter finished and correct? It is ready only when issues is empty,
          status is complete, no double-brace markup or IF/END_IF marker appears anywhere
          in letter_text (body, [hdr], [ftr]), every conditional has included true or false
          matching its data value (Yes-like kept, No-like removed), and no value reads as
          broken ("None", "null", empty where a name/amount belongs, doubled "$$").
          Template wording outside the conditional markers, such as a section heading left
          above a removed block, is the template author's and is NOT a defect.
        criteria:
          true: Clean report and a letter with every field filled and conditionals resolved per the data.
          false: Any reported issue, leftover markup, unresolved or wrongly resolved conditional, or broken value.
    thresholds:
      ready: 0.2
    inputs_to: by-readiness

  - name: by-readiness
    kind: router
    description: A ready letter ends the run; anything else goes to repair.
    branch_on: ready
    branches:
      "true": end
      "false": repair-letter

  - name: repair-letter
    kind: client_task
    description: Resolve the reported gaps from the data and regenerate the letter.
    inputs:
      - name: output_file
        type: string
      - name: issues
        type: list[*]
      - name: conditionals
        type: object
      - name: letter_text
        type: string
      - name: template_path
        type: string
      - name: data_path
        type: string
      - name: output_path
        type: string
    template: assets/repair_letter.md
    references:
      - path: references/docx-template-filling.md
        description: >
          python-docx template-filling guide — the script's CLI flags (--condition, --map,
          --record), split-placeholder handling, headers/footers, nested tables,
          conditional-section rules, pitfalls. Load before rerunning or hand-editing the .docx.
    outputs:
      - name: repair_notes
        type: string
        description: What was wrong, the exact fix (rerun command or edit), and anything left unresolved.
    inputs_to: end

  - name: end
    kind: end
    description: The filled offer letter saved at output_file, with what was written into it.
    inputs:
      - name: output_file
        type: string
      - name: filled_placeholders
        type: object
      - name: conditionals
        type: object

anti_patterns:
  - Replacing placeholders run by run (misses {{CANDI + DATE_NAME}} split across runs).
  - Processing only doc.paragraphs and skipping tables, nested tables, headers and footers.
  - Leaving {{IF_...}} / {{END_IF_...}} markers in the final letter, or keeping a block whose flag is No.
  - Inventing a value the data file does not hold, or hardcoding values instead of reading the data.
  - Writing the output anywhere other than the exact path the task names.
```
