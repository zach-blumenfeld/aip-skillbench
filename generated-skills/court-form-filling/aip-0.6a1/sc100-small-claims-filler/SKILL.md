---
name: sc100-small-claims-filler
description: Fill the California Small Claims Court Plaintiff's Claim (form SC-100) PDF from a plain-language case description — plaintiff/defendant names and addresses, claim amount, why owed, dates, asked-to-pay, venue, yes/no items, signature date — leaving court/clerk and unmentioned fields empty, and verify the saved PDF. Also fills other fillable PDF forms by field tooltip, and non-fillable PDFs by visually placed text annotations. Use for court form filling, small claims, SC-100, pypdf AcroForm filling, encrypted or XFA PDF forms.
license: Proprietary. source/pdf/LICENSE.txt has complete terms
compatibility: Python 3.10+ with pypdf, cryptography (the official SC-100 is AES-encrypted), and pillow; poppler-utils (pdftoppm) for page rendering.
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
  Fill a PDF court form, chiefly the California small claims Plaintiff's Claim (SC-100),
  from a free-text case description and save a verified filled copy. A script inspects the
  form (decrypting it; the official SC-100 is AES-encrypted and XFA-backed) and routes:
  SC-100 forms whose field ids match the bundled field map get deterministic filling — the
  agent extracts the case facts, a decision answers the form's yes/no and venue questions,
  and a script maps everything onto exact field ids, computes item 10 (over $2,500) from the
  amount, formats dates, and never touches court/clerk fields; other fillable forms are
  mapped by field tooltip; non-fillable forms get visually placed text annotations. Every
  path writes the output PDF and checks it.

trigger_when:
  - A task asks to fill the California Small Claims form SC-100 (Plaintiff's Claim and ORDER to Go to Small Claims Court) from a case description.
  - A task gives a blank court or government PDF form plus a narrative of facts and asks for a filled PDF saved to a path.
  - Someone needs to sue in California small claims and wants the plaintiff's claim form completed.
  - Any fillable (AcroForm) or non-fillable PDF form must be filled programmatically from text facts.

do_not_use_when:
  - The task is to read, extract text/tables from, merge, split, or create PDFs with no form to fill (see references/pdf-processing.md for those operations).
  - The task asks for legal advice about whether or where to sue rather than completing the form.

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - pypdf>=5.0
    - cryptography>=3.1
    - pillow
  tools:
    - pdftoppm

steps:
  - name: inspect-form
    kind: execution
    description: >
      Open the blank form (decrypting it with the empty user password), list every fillable
      field with page, type, rect, tooltip (the printed label), and checkbox/radio/choice
      values, and choose the route: sc100 when every slot of the bundled SC-100 field map
      resolves to exactly one field; fillable for any other AcroForm (including an SC-100
      revision whose ids changed); non_fillable when the PDF has no form fields.
    inputs:
      - name: form_pdf_path
        type: string
        description: Absolute path of the blank PDF form (the task statement names it, e.g. /root/sc100-blank.pdf).
      - name: output_pdf_path
        type: string
        description: Absolute path where the filled PDF must be saved (e.g. /root/sc100-filled.pdf).
      - name: case_description
        type: string
        description: The full task statement, verbatim — the case narrative plus any filling instructions (which fields to leave empty, filing date, and so on).
      - name: date_format
        type: string
        description: Date format the task requires, written with YYYY, MM, DD tokens (e.g. "YYYY-MM-DD" when the task says "xxxx-xx-xx"). Use YYYY-MM-DD if the task names none.
    script: scripts/inspect_form.py
    assets:
      - assets/sc100_field_map.json
    outputs:
      - name: form_route
        type: string
        description: sc100, fillable, or non_fillable.
      - name: form_fields
        type: list[*]
        description: Fillable fields (field_id, page, type, rect, tooltip, checked_value / radio_options / choice_options); empty for non-fillable forms.
      - name: form_summary
        type: string
        description: Page and field counts, and why the route was chosen.
    inputs_to: route-by-form

  - name: route-by-form
    kind: router
    description: Deterministic SC-100 path, tooltip-mapped path for other fillable forms, or visual annotation path.
    branch_on: form_route
    branches:
      sc100: extract-sc100-case
      fillable: map-generic-fields
      non_fillable: render-pages

  - name: extract-sc100-case
    kind: client_task
    description: Pull the SC-100 facts (parties, addresses, amount, why owed, dates, calculation, venue ZIP, filing date) out of the case description into one structured object, leaving unmentioned slots empty.
    inputs:
      - name: case_description
        type: string
      - name: date_format
        type: string
    template: assets/extract_sc100_case.md
    assets:
      - assets/sc100_case_schema.json
    references:
      - path: references/sc100-guide.md
        description: Item-by-item SC-100 guide — who fills which area, what each item 1-11 asks, venue options a-e, attachments (SC-100A, SC-103, SC-101, MC-031). Load when a slot's meaning or whether to fill it is unclear.
    outputs:
      - name: sc100_case
        type: object
        description: The case facts in the shape of assets/sc100_case_schema.json (plaintiffs, defendants, claim_amount, why_owed, incident_date or period_start/period_through, how_calculated, needs_more_space, asked_no_explanation, venue_other_specify, venue_zip, public_claim_filed_date, court_name_address, filing_date).
    inputs_to: sc100-facts

  - name: sc100-facts
    kind: decision
    description: Answer the SC-100 yes/no items and the venue question from the case. Facts the case never raises are answered false (the ordinary case), not guessed true.
    inputs:
      - name: case_description
        type: string
    questions:
      asked_before_suing:
        type: noul
        instructions: Item 4 — did the plaintiff ask the defendant to pay (or, for property, to return it) before suing, in person, in writing, by text/email, or by phone?
        criteria:
          true: The case says the plaintiff asked, requested, demanded, texted, emailed, called, or sent a letter asking for the money or property, even if the defendant ignored it.
          false: The case says they did not ask, or never mentions any request to the defendant.
      venue_basis:
        type: choice
        instructions: >
          Item 5 — why is the claim filed at this courthouse? Pick the one box that applies.
          Filing "where the defendant lives" is defendant_or_contract_or_injury.
        criteria:
          defendant_or_contract_or_injury: "5a: where the defendant lives or does business, where the plaintiff's property was damaged, where the plaintiff was injured, or where a contract was made, signed, performed, or broken by the defendant (or where the defendant lived/did business when making it)."
          consumer_contract: "5b: where the buyer or lessee signed, lives now, or lived when the contract was made, for an offer or contract for personal, family, or household goods, services, or loans."
          retail_installment: "5c: where the buyer signed, lives now, or lived when the contract was made, for a retail installment contract such as a credit card."
          vehicle_finance: "5d: where the buyer signed, lives now, or lived when the contract was made, or where the vehicle is permanently garaged, for a vehicle finance sale."
          other: "5e: some other stated reason that fits none of the above."
      attorney_fee_dispute:
        type: noul
        instructions: Item 7 — is the claim about a fee dispute between an attorney and a client?
      fee_arbitration_done:
        type: noul
        instructions: Item 7 follow-up — if it is an attorney-client fee dispute, has the dispute already gone through fee arbitration? Answer false when it is not a fee dispute.
      suing_public_entity:
        type: noul
        instructions: Item 8 — is any defendant a public entity (a city, county, state agency, school district, public transit or utility district)? An individual person or private business is false.
      over_12_claims:
        type: noul
        instructions: Item 9 — has the plaintiff filed more than 12 other small claims in California within the last 12 months? "First time suing" or no mention is false.
      defendant_military:
        type: noul
        instructions: Is any defendant on active military duty? False unless the case says so.
      plaintiff_fictitious_name:
        type: noul
        instructions: Is a plaintiff doing business under a fictitious business name (a DBA)? False for an individual suing in their own name.
      plaintiff_payday_lender:
        type: noul
        instructions: Is a plaintiff a "licensee" or "deferred deposit originator" (payday lender) under Financial Code sections 23000 et seq.? False unless the case says so.
    thresholds:
      asked_before_suing: 0.3
      venue_basis: 0.5
      suing_public_entity: 0.3
      over_12_claims: 0.3
    inputs_to: build-sc100-values

  - name: build-sc100-values
    kind: execution
    description: >
      Map the case facts and decision answers onto exact SC-100 field ids: captions, party
      blocks (mailing only if different), amount, 3a-3c, exactly one box for items 4, 5, 7, 8,
      9, 10 (10 computed from the amount, strictly over $2,500), item 6 ZIP, signature name and
      date; dates in date_format; court/clerk fields refused. Notes list required attachments
      and anything left blank.
    inputs:
      - name: sc100_case
        type: object
      - name: form_fields
        type: list[*]
      - name: date_format
        type: string
      - name: asked_before_suing
        type: boolean
      - name: venue_basis
        type: string
      - name: attorney_fee_dispute
        type: boolean
      - name: fee_arbitration_done
        type: boolean
      - name: suing_public_entity
        type: boolean
      - name: over_12_claims
        type: boolean
      - name: defendant_military
        type: boolean
      - name: plaintiff_fictitious_name
        type: boolean
      - name: plaintiff_payday_lender
        type: boolean
    script: scripts/build_sc100_values.py
    assets:
      - assets/sc100_field_map.json
    outputs:
      - name: sc100_field_values
        type: list[*]
        description: One object per field to fill (field_id, page, value, slot). Fields not listed stay empty.
      - name: sc100_mapping_notes
        type: list[*]
        description: Attachments the filer must add (SC-100A, SC-103, SC-101, MC-031) and fields left blank for lack of facts. Report them to the user.
    inputs_to: fill-sc100

  - name: fill-sc100
    kind: execution
    description: Write the SC-100 values into the blank form, drop the XFA packet so viewers show the AcroForm values, save an unencrypted PDF at output_pdf_path, and read it back to confirm every value persisted and no other field holds a value.
    inputs:
      - name: form_pdf_path
        type: string
      - name: output_pdf_path
        type: string
      - name: sc100_field_values
        type: list[*]
    script: scripts/fill_form.py
    outputs:
      - name: sc100_fill_report
        type: object
        description: output_pdf, fields_set, encrypted, mismatches, unexpected_nonempty, verified.
    inputs_to: end

  - name: map-generic-fields
    kind: client_task
    description: For a fillable form the SC-100 map does not cover, decide which fields the case supplies and their exact values, from the field tooltips, ids, and (if needed) rendered pages.
    inputs:
      - name: case_description
        type: string
      - name: form_fields
        type: list[*]
      - name: form_summary
        type: string
      - name: date_format
        type: string
    template: assets/map_generic_fields.md
    references:
      - path: references/sc100-guide.md
        description: What each SC-100 item asks and which areas are court-filled. Load when the form is an SC-100 revision the field map did not match.
      - path: references/pdf-processing.md
        description: pypdf, pdfplumber, reportlab, and poppler command-line recipes. Load only if the form needs inspection beyond tooltips (e.g. extracting label text near a field).
      - path: references/pdf-advanced.md
        description: pypdfium2, pdf-lib, pdfjs, qpdf, and troubleshooting (encrypted, corrupted PDFs, text extraction with coordinates). Load only if the form will not open, will not fill, or label positions must be extracted programmatically.
    outputs:
      - name: generic_field_values
        type: list[*]
        description: One object per field to fill with field_id, page, and value (checkbox = its checked_value, radio/choice = one of its option values, text = string).
    inputs_to: fill-generic

  - name: fill-generic
    kind: execution
    description: Validate every field id, page, and value against the form, write the values, save output_pdf_path unencrypted without the XFA packet, and verify by reading it back. On an error it stops with the exact message; fix generic_field_values and rerun.
    inputs:
      - name: form_pdf_path
        type: string
      - name: output_pdf_path
        type: string
      - name: generic_field_values
        type: list[*]
    script: scripts/fill_form.py
    outputs:
      - name: generic_fill_report
        type: object
        description: output_pdf, fields_set, encrypted, mismatches, unexpected_nonempty, verified.
    inputs_to: end

  - name: render-pages
    kind: execution
    description: The form has no fillable fields; render each page to a PNG (longest side 1000 px) next to the output path, with image and PDF page sizes.
    inputs:
      - name: form_pdf_path
        type: string
      - name: output_pdf_path
        type: string
    script: scripts/render_pages.py
    outputs:
      - name: page_images
        type: list[*]
        description: page_number, image_path, image_width, image_height, pdf_width, pdf_height per page.
    inputs_to: locate-boxes

  - name: locate-boxes
    kind: client_task
    description: Visually find each entry area and its label on the page images, build the fields.json object with non-intersecting label and entry boxes, and validate it with check_bounding_boxes.py and inspected validation images before handing it on.
    inputs:
      - name: case_description
        type: string
      - name: form_pdf_path
        type: string
      - name: page_images
        type: list[*]
      - name: date_format
        type: string
    template: assets/locate_boxes.md
    assets:
      - assets/fields_json_example.json
    outputs:
      - name: annotation_fields
        type: object
        description: fields.json object — pages (page_number, image_width, image_height) and form_fields (page_number, description, field_label, label_bounding_box, entry_bounding_box, entry_text) in image pixel coordinates.
    inputs_to: annotate-form

  - name: annotate-form
    kind: execution
    description: Re-run the bounding-box check (stops on any intersection or an entry box shorter than its font size), convert image boxes to PDF coordinates, and add each entry_text as a FreeText annotation; save output_pdf_path.
    inputs:
      - name: form_pdf_path
        type: string
      - name: output_pdf_path
        type: string
      - name: annotation_fields
        type: object
    script: scripts/annotate_form.py
    outputs:
      - name: annotation_report
        type: object
        description: output_pdf, annotations_added, bounding_box_check messages.
    inputs_to: end

  - name: end
    kind: end
    description: The filled PDF is saved at output_pdf_path and verified (its fill report or annotation report is in the state; on the SC-100 path, also relay sc100_mapping_notes).
    inputs:
      - name: output_pdf_path
        type: string

anti_patterns:
  - Filling court/clerk areas (case number, case name, trial date/time/department, clerk signature, "Need help?" advisor boxes) or fields the case never mentions, such as a mailing address identical to the street address or the court address when no court is named.
  - Inventing values to make the form look complete (an email, a defendant phone, an agent for service for an individual defendant).
  - Checking both or neither box of a Yes/No pair; answering item 10 by judgment instead of comparing the amount to $2,500 (exactly $2,500 is No).
  - Putting a date span in the single "Date" of item 3b, or a single date in "Date started"/"Through".
  - Writing dates in a format other than the one the task asks for, or the amount with "$" or thousands separators when the form prints "$".
  - Setting a checkbox to "Yes", "On", or "X" instead of its checked_value (e.g. "/1" or "/2" on SC-100).
  - Reading the encrypted SC-100 without the cryptography package, or saving an output that is still encrypted or keeps the XFA packet (other readers and viewers then miss the values).
  - Skipping the visual validation of bounding boxes on a non-fillable form, or letting a label box and entry box overlap.
  - Doing a failed script step by hand instead of fixing its inputs and rerunning it.
```
