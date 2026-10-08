---
name: pdf-form-filling
description: Fill PDF forms from case facts or user data — court forms like California small claims SC-100 (Plaintiff's Claim and ORDER to Go to Small Claims Court), government, legal, and any fillable AcroForm/XFA-hybrid PDF, plus non-fillable scanned/flat forms via positioned text annotations. Inspects fields with meaning labels, maps facts to field IDs, enforces form rules (clerk-only fields, Yes/No checkbox pairs, amount thresholds), writes the filled PDF, and verifies it by read-back. Use whenever a task says fill out, complete, or populate a PDF form.
license: Proprietary. source/pdf/LICENSE.txt has complete terms
compatibility: Python 3 with pypdf (+ cryptography for encrypted forms), Pillow, and poppler-utils (pdftoppm, pdftotext).
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
  Turn a blank PDF form plus a description of the facts (names, addresses, amounts, dates,
  what happened) into a correctly filled PDF. A script inspects the form and labels every
  field — exactly for known court forms such as California SC-100, heuristically from the
  printed text otherwise — the agent maps facts to field IDs, and a script validates the plan
  against the PDF and the form's rules (clerk-only fields, Yes/No checkbox pairs, amount
  thresholds, repeated headers), writes the file, and reads it back for review. Flat forms
  with no fields get the bounding-box annotation workflow instead.

trigger_when:
  - A task asks to fill out, complete, or populate a PDF form and save the filled copy.
  - A court or legal form (e.g. California small claims SC-100, Plaintiff's Claim) must be completed from a case description.
  - A blank government, application, or intake PDF form must be filled from user-supplied data.

do_not_use_when:
  - The task only reads, extracts, merges, splits, or creates PDFs with no form to fill (see references/pdf-operations.md directly).
  - The user wants legal advice about whether or what to claim rather than a filled form.

steps:
  - name: inspect-form
    kind: execution
    description: Open the PDF (decrypting if needed), list its fillable fields with page, type, checkbox values and a meaning label, match a known form profile, and render page images.
    inputs:
      - name: pdf_path
        type: string
        description: Absolute path of the blank form, e.g. /root/sc100-blank.pdf.
      - name: output_pdf
        type: string
        description: Absolute path the filled PDF must be written to, exactly as the task names it.
      - name: case_facts
        type: string
        description: Everything the task says about the people, amounts, dates, and events, verbatim, plus any explicit field instructions.
      - name: work_dir
        type: string
        description: Absolute scratch directory for page images and intermediate files (outside the output location).
    script: scripts/inspect_form.py
    assets:
      - assets/form-profiles.json
    timeout: 180
    inputs_to: route-by-form-type

  - name: route-by-form-type
    kind: router
    description: Forms with fillable fields are filled by field ID; flat forms get positioned text annotations.
    branch_on: is_fillable
    branches:
      "true": map-fields
      "false": locate-boxes

  - name: map-fields
    kind: client_task
    description: Map every fact to the right field ID and value, leaving clerk/court-only fields blank.
    inputs:
      - name: case_facts
        type: string
      - name: form_fields
        type: list[*]
        description: Fields from inspect-form with field_id, page, type, checked_value, label, who_fills.
      - name: form_notes
        type: list[*]
        description: Form-specific rules from the matched profile (empty for unknown forms).
      - name: profile_name
        type: string
        description: Matched form profile, e.g. SC-100; empty string when unknown.
      - name: page_images
        type: list[*]
      - name: output_pdf
        type: string
    template: assets/map-fields.md
    references:
      - path: references/sc100-guide.md
        description: California SC-100 small claims form, item by item — which fact goes in which field, who fills what, Yes/No checkbox values, venue (item 5) choices, amount limits, gotchas. Read before mapping whenever profile_name is SC-100 or the form is a California small-claims form.
      - path: references/pdf-operations.md
        description: General pypdf / poppler recipes (merge, split, extract text, create PDFs). Only if the task also needs PDF work beyond filling this form.
      - path: references/pdf-advanced.md
        description: Advanced PDF libraries and troubleshooting (encrypted or corrupted PDFs, pypdfium2, pdf-lib). Only if the PDF fails to open or needs repair.
    inputs_to: fill-fields

  - name: fill-fields
    kind: execution
    description: Validate field IDs, pages, and checkbox/choice values against the PDF and the form profile's rules, auto-apply deterministic fixes, then write the filled PDF.
    inputs:
      - name: pdf_path
        type: string
      - name: output_pdf
        type: string
      - name: field_values
        type: list[*]
        description: Objects with field_id, value, and optional page.
    script: scripts/fill_fields.py
    assets:
      - assets/form-profiles.json
    timeout: 120
    inputs_to: fill-gate

  - name: fill-gate
    kind: router
    description: Any validation error means nothing was written; go back and fix the plan.
    branch_on: fill_ok
    branches:
      "true": verify-output
      "false": map-fields

  - name: locate-boxes
    kind: client_task
    description: On the page images, find label and entry bounding boxes for every field and pair each entry with its fact.
    inputs:
      - name: case_facts
        type: string
      - name: page_images
        type: list[*]
        description: Page PNGs with pixel width and height.
      - name: output_pdf
        type: string
    template: assets/locate-boxes.md
    assets:
      - assets/fields-format.md
    inputs_to: check-boxes

  - name: check-boxes
    kind: execution
    description: Reject intersecting label/entry boxes and entry boxes shorter than their font size; draw red entry and blue label rectangles on validation images.
    inputs:
      - name: fields_spec
        type: object
        description: The fields.json plan with pages and form_fields.
      - name: page_images
        type: list[*]
      - name: work_dir
        type: string
    script: scripts/check_boxes.py
    timeout: 120
    inputs_to: boxes-gate

  - name: boxes-gate
    kind: router
    description: Any FAILURE in the automated box check sends the plan back for correction.
    branch_on: boxes_ok
    branches:
      "true": inspect-boxes
      "false": locate-boxes

  - name: inspect-boxes
    kind: decision
    description: Visually confirm, on the validation images, that every rectangle sits where it should before anything is written.
    inputs:
      - name: validation_images
        type: list[*]
        description: Page PNGs with red entry and blue label rectangles; open every one.
      - name: fields_spec
        type: object
    questions:
      boxes_accurate:
        type: noul
        instructions: Looking at every validation image, are all rectangles correctly placed?
        criteria:
          true: Every red rectangle covers only blank entry area and contains no printed text; checkbox red rectangles are centered on the square; every blue rectangle covers its label text.
          false: Any red rectangle overlaps printed text, misses its blank area or checkbox square, or any blue rectangle misses its label.
    thresholds:
      boxes_accurate: 0.3
    inputs_to: boxes-visual-gate

  - name: boxes-visual-gate
    kind: router
    description: Misplaced rectangles go back to locate-boxes; accurate ones get written.
    branch_on: boxes_accurate
    branches:
      "true": fill-annotations
      "false": locate-boxes

  - name: fill-annotations
    kind: execution
    description: Convert entry boxes from image pixels to PDF points and add each entry_text as a FreeText annotation.
    inputs:
      - name: pdf_path
        type: string
      - name: fields_spec
        type: object
      - name: output_pdf
        type: string
    script: scripts/fill_annotations.py
    timeout: 120
    inputs_to: verify-output

  - name: verify-output
    kind: execution
    description: Read the written PDF back, list every filled value with its label, intended-vs-actual mismatches, and still-empty filer fields, and render the filled pages.
    inputs:
      - name: output_pdf
        type: string
      - name: is_fillable
        type: boolean
      - name: work_dir
        type: string
    script: scripts/verify_output.py
    assets:
      - assets/form-profiles.json
    timeout: 180
    inputs_to: review-output

  - name: review-output
    kind: decision
    description: Judge whether the written PDF faithfully and completely carries the case facts.
    inputs:
      - name: case_facts
        type: string
      - name: verify_report
        type: string
        description: Filled fields with labels, plus filer fields left empty (or annotations for flat forms).
      - name: readback_mismatches
        type: list[*]
      - name: output_images
        type: list[*]
    questions:
      output_correct:
        type: noul
        instructions: >
          Compare verify_report (and the state's fill_warnings and auto_changes, if present)
          against case_facts. Is the filled PDF complete and correct? verify_report is read
          back from the file and is authoritative for values; open output_images only to judge
          placement, since missing system fonts can render text and checkbox marks blank.
        criteria:
          true: Every fact with a home on the form is in the right field, copied exactly; every yes/no question the form asks is answered; every still-empty filer field is genuinely not applicable; no clerk/court-only field holds data; readback_mismatches is empty.
          false: A fact is missing, misplaced, altered, or invented; a required question is unanswered; a clerk/court field is filled; or there is a readback mismatch.
    thresholds:
      output_correct: 0.25
    inputs_to: review-gate

  - name: review-gate
    kind: router
    description: A correct PDF finishes the run; anything wrong is fixed on the path that produced it.
    branch_on: output_correct
    branches:
      "true": end
      "false": fix-route

  - name: fix-route
    kind: router
    description: Send corrections back to field mapping (fillable) or box placement (flat form).
    branch_on: is_fillable
    branches:
      "true": map-fields
      "false": locate-boxes

  - name: end
    kind: end
    description: The filled PDF at output_pdf, verified by read-back.
    inputs:
      - name: output_pdf
        type: string
      - name: verify_report
        type: string
      - name: output_correct
        type: boolean

anti_patterns:
  - Writing the filled PDF with ad-hoc code (fillpdf, pdfrw, a fresh pypdf script) instead of scripts/fill_fields.py — it skips the field/value validation, keeps the stale XFA layer, and loses the form-rule checks.
  - Filling clerk-only areas (case number, trial date/time/department, clerk signature) or the court's "Need help?" boxes because the facts mention a hearing or a court.
  - Checking both boxes of a Yes/No pair, or setting a checkbox to "Yes"/"On" instead of its checked_value (SC-100 uses "/1" for Yes and "/2" for No).
  - Leaving a yes/no question unanswered because the facts are silent — silence about public entities, fee disputes, or prior filings means No.
  - Paraphrasing or "correcting" names, addresses, amounts, or dates from the facts; copy them exactly (only drop the "$" where the form prints it).
  - Inventing facts (phone numbers, emails, zip codes, signatures) the task does not give; leave the field blank instead of writing N/A.
  - Putting the mailing address or agent-for-service fields in when the facts give no separate mailing address or the defendant is an individual.
  - Skipping the validation-image inspection on flat forms, or putting the entry box over the label text or a checkbox's caption instead of the square.
  - Saving test inputs, page images, or scratch JSON next to the output PDF or inside the skill folder; use work_dir.
```
