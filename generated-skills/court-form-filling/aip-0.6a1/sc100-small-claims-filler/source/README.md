# sc100-small-claims-filler — provenance and compilation notes

## Provenance

- `source/pdf/` — the curated `pdf` Agent Skill, copied verbatim: `SKILL.md`, `forms.md`,
  `reference.md`, `LICENSE.txt` (proprietary, Anthropic), and `scripts/` (8 files).
- Task context (not copied; read at authoring time): the task statement (fill the
  California Small Claims form at `/root/sc100-blank.pdf` from a case description, save
  to `/root/sc100-filled.pdf`, only necessary fields, dates `xxxx-xx-xx`), the real blank
  form `sc100-blank.pdf` (SC-100 Rev. January 1, 2026, 6 pages, 103 AcroForm fields, AES
  encrypted with an empty user password, XFA packet present), and the container
  Dockerfile (Ubuntu 24.04, python3, poppler-utils; pip: pypdf 5.1.0, fillpdf, pdfrw,
  PyPDF2, reportlab 4.2.5, cryptography 43.0.3; pillow comes in as a reportlab dependency).
- SC-100 domain content in `references/sc100-guide.md` and `assets/sc100_field_map.json`
  was taken from the blank form itself: its printed text (`pdftotext -layout`), the field
  tooltips (/TU), and rendered pages used to confirm which checkbox is Yes vs No (by x
  position) and which box belongs to each item.

## Intent

A downstream agent receives a task statement plus a blank court PDF and must produce the
filled PDF autonomously. The `pdf` skill supplies the generic method (check for fillable
fields → extract fields → map values → fill and validate; or visual bounding boxes →
validate → annotate). This skill keeps that method for any form and adds a deterministic
SC-100 path, because the hard part for this task type is SC-100 domain knowledge: which
fields are court-only, which yes/no items must always be answered, how item 3b splits a
date vs a period, item 10's $2,500 threshold, checkbox on-values (/1, /2), date format,
and the encrypted/XFA file.

## Component-kind choices

| Step | Kind | Why |
|---|---|---|
| inspect-form | execution | Detecting fillable fields, extracting field info, and checking whether the SC-100 map resolves are deterministic code (forms.md step 1 + extract_form_field_info.py). Decrypts first — without `cryptography` pypdf cannot read the official form at all. |
| route-by-form | router | forms.md branches on fillable vs non-fillable; added a third branch for SC-100 so the known form gets the deterministic map, while a changed revision or another form falls back to tooltip mapping instead of failing. |
| extract-sc100-case | client_task | Reading a free-text narrative into structured facts (address splitting, which text is "why owed" vs "how calculated", date vs span) is generation from language; the output is a typed object so everything after it is code. |
| sc100-facts | decision | Items 4, 5, 7, 8, 9 and the plaintiff/defendant flags are judgments with a fixed answer space (yes/no; venue a–e). Typed answers feed the script; thresholds flag the ones whose error is costly (asked-before-suing, venue, public entity, >12 claims). |
| build-sc100-values | execution | Field-id lookup, exactly-one-box rules, mailing-only-if-different, item 10 numeric threshold, date/amount formatting, and the court-field blacklist are deterministic rules — scripted rather than prose. |
| fill-sc100 / fill-generic | execution | fill_fillable_fields.py logic (id/page/value validation, pypdf selection-list patch, NeedAppearances) plus read-back verification, XFA removal, unencrypted output. Two steps share one script because each key has one producer per AIP. |
| map-generic-fields | client_task | For an unknown form, deciding field purpose from tooltips/rendered pages is agent judgment with open-ended output. |
| render-pages | execution | Page rendering is mechanical (replaces convert_pdf_to_images.py). |
| locate-boxes | client_task | Visual bounding-box location needs the agent's vision; the template carries the forms.md layout patterns, checkbox rules, and the mandatory check-script + validation-image loop. |
| annotate-form | execution | Coordinate transform + FreeText annotations (fill_pdf_form_with_annotations.py), gated by re-running check_bounding_boxes. |

## Source → skill map (completeness check)

`source/pdf/SKILL.md`
- Overview, Quick Start, pypdf (merge/split/metadata/rotate), pdfplumber (text, tables, pandas), reportlab (canvas, platypus), CLI tools (pdftotext, qpdf, pdftk), OCR, watermark, image extraction, password protection, quick-reference table, next steps → `references/pdf-processing.md` (verbatim body), referenced from `map-generic-fields` and `do_not_use_when`.
- "If you need to fill out a PDF form, read forms.md and follow its instructions" → the whole procedure.

`source/pdf/forms.md`
- "CRITICAL: complete these steps in order" → enforced by the step graph.
- Check fillable fields first, then branch → `inspect-form` + `route-by-form`.
- Fillable: extract field info (field_id, page, rect, type, checked/unchecked values, radio_options, choice_options) → `inspect-form` output `form_fields` (same shape, plus tooltip).
- Fillable: convert to PNGs and analyze images to determine each field's purpose (convert PDF rect to image coords) → SC-100: done once at authoring time and frozen into `assets/sc100_field_map.json`; generic: `map_generic_fields.md` tells the agent to use tooltips and render pages (`pdftoppm`) / `pdftotext -layout` when tooltips are unclear, with the y-flip rule.
- field_values.json format and checkbox/radio value rules → `map_generic_fields.md` rules + `build_sc100_values.py` (uses each checkbox's checked_value).
- Run fill_fillable_fields.py; it validates ids/values; fix and retry on errors → `fill-sc100`/`fill-generic` (`pdf_form_lib.fill_and_verify`), the template's retry instruction, and `aip resume` re-answering the client task.
- Non-fillable Steps 1–4 (visual analysis, layout patterns: label inside box / before line / under line / above line, checkbox square targeting; fields.json format with pages + form_fields, font_size default 14, font_color; validation images red/blue; automated intersection + height check; manual inspection criteria; annotate) → `render-pages`, `assets/locate_boxes.md`, `assets/fields_json_example.json`, `scripts/check_bounding_boxes.py`, `scripts/create_validation_image.py`, `annotate-form`.

`source/pdf/scripts/`
- check_fillable_fields.py → `inspect_form.py` (route `non_fillable` when no fields).
- extract_form_field_info.py → `pdf_form_lib.get_field_info` (same logic; adds decryption, tooltip, rounded rects; the "unexpected checkbox states" print becomes a `warning` key on the field).
- fill_fillable_fields.py → `pdf_form_lib.fill_and_verify` + `fill_form.py` (same validation, monkeypatch, auto_regenerate=False, NeedAppearances).
- convert_pdf_to_images.py → `render_pages.py` (pdftoppm `-scale-to 1000`, same 1000 px cap).
- check_bounding_boxes.py, create_validation_image.py → copied verbatim to `scripts/`.
- fill_pdf_form_with_annotations.py → `annotate_form.py` (same transform and FreeText call, plus the bounding-box gate and decryption).
- check_bounding_boxes_test.py → dropped (see below).

`source/pdf/reference.md` → `references/pdf-advanced.md` (verbatim), referenced from `map-generic-fields`. Its form-filling tip "pre-validate form fields before processing" is implemented by the fill scripts.

`source/pdf/LICENSE.txt` → kept in source; frontmatter `license` points to it.

Task statement rules → "only necessary fields, leave court-filled/optional/unmentioned empty" (`build_sc100_values.py` fills only supplied facts and refuses `never_fill` ids; `extract_sc100_case.md` rules; anti_patterns), date format (start input `date_format`, script formatting).

## Deliberate-drop log

- `check_bounding_boxes_test.py` — unit tests for the checker, "not run automatically in CI; just for documentation". Not actionable at run time; kept in `source/`.
- pdf2image dependency of `convert_pdf_to_images.py` — not installed in the container; replaced by poppler's `pdftoppm`, which is.
- The `description` key in each field_values.json entry — informational only; the fill script ignores it, so generic_field_values asks for field_id/page/value.
- "Unable to determine location for field id ..., ignoring" print — such fields are still skipped, silently (scripts' stdout must be pure JSON).
- Exact SC-100 field-level judgment calls made at authoring time: the page 2–4 "Plaintiff (list names)" caption is treated as plaintiff-filled; page 1 "Case Name" is treated as part of the court's case-number box and never filled; required Yes/No items (4, 7, 8, 9, 10) are always answered with exactly one box, defaulting to No when the case never raises the topic.
