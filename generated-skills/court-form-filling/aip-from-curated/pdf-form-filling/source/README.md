# Source and provenance — pdf-form-filling

## What this skill was compiled from

`source/pdf/` is a verbatim copy of the curated Agent Skill `pdf` (Anthropic, proprietary;
terms in `source/pdf/LICENSE.txt`):

| File | Role in the original |
|---|---|
| `SKILL.md` | General PDF toolkit guide (pypdf, pdfplumber, reportlab, poppler/qpdf/pdftk CLIs, OCR, watermark, encryption); points to `forms.md` for form filling. |
| `forms.md` | The form-filling workflow: fillable-field path and non-fillable (annotation) path. |
| `reference.md` | Advanced libraries (pypdfium2, pdf-lib, pdfjs-dist), CLI options, troubleshooting. |
| `scripts/*.py` | `check_fillable_fields`, `extract_form_field_info`, `convert_pdf_to_images`, `fill_fillable_fields`, `create_validation_image`, `check_bounding_boxes` (+ `_test`), `fill_pdf_form_with_annotations`. |

Task context used in addition (read-only, not copied into the pack): the task container's
Dockerfile (Ubuntu 24.04, python3, poppler-utils, pypdf 5.1.0, fillpdf, pdfrw, PyPDF2,
reportlab 4.2.5 → Pillow, cryptography 43) and the real input file `sc100-blank.pdf`
(California Judicial Council SC-100, Rev. January 1, 2026, 294,816 bytes, untruncated).
Inspecting that file showed facts the curated skill does not cover, which became the
SC-100 profile and gotchas:

- AES-encrypted (V4) with an empty user password → pypdf needs `cryptography`.
- XFA/AcroForm hybrid with a Reader-extensions signature (`/Perms /UR3`).
- 103 widget fields with long XFA-style IDs (`SC-100[0].Page2[0].List1[0]...`).
- Yes/No questions are pairs of separate checkboxes with on-values `/1` (Yes) and `/2` (No);
  item 5 a–e are five checkboxes with on-values `/1`…`/5`.
- Print/Save/Reset are pushbuttons that the original extractor reported as checkboxes
  with no checked value.
- Clerk-only areas (case number, trial order, clerk signature) and court-only "Need help?"
  boxes are ordinary text fields that an agent would otherwise fill.

## Intent

One coherent unit: given a blank PDF form and the facts, produce the filled PDF, validated
and read back. The original skill's broader PDF toolkit is kept as on-demand references.

## Graph and step-kind choices

```
inspect-form (execution) → route-by-form-type (router: is_fillable)
  true  → map-fields (client_task) → fill-fields (execution) → fill-gate (router: fill_ok)
            false → map-fields          true → verify-output
  false → locate-boxes (client_task) → check-boxes (execution) → boxes-gate (router: boxes_ok)
            false → locate-boxes        true → inspect-boxes (decision) → boxes-visual-gate (router)
                                             false → locate-boxes   true → fill-annotations (execution) → verify-output
verify-output (execution) → review-output (decision) → review-gate (router: output_correct)
  true → end      false → fix-route (router: is_fillable) → map-fields | locate-boxes
```

| Step | Kind | Why |
|---|---|---|
| inspect-form | execution | Fillable-or-not, field extraction, page rendering, and known-form label lookup are deterministic. Merges the original `check_fillable_fields`, `extract_form_field_info`, `convert_pdf_to_images` into one call, and adds a meaning `label` per field (exact from `assets/form-profiles.json` for SC-100, else nearest printed text via `pdftotext -bbox-layout`) so the agent doesn't have to eyeball 100+ field IDs. |
| route-by-form-type | router | forms.md's "depending on the result go to Fillable / Non-fillable". |
| map-fields | client_task | Mapping free-text facts onto fields is generation/judgment over open-ended input; no fixed answer space. |
| fill-fields | execution | Field-ID/page/value validation (original `fill_fillable_fields`) plus scriptable form rules: clerk/court/button fields forbidden, exclusive Yes/No pairs, item 10 derived from the item-3 amount (> $2,500), "$" stripped where pre-printed, header copied to pages 2–4, small-claims limits warned. Nothing is written when there is an error. |
| fill-gate | router | forms.md: "if it prints error messages, correct the appropriate fields and try again." |
| locate-boxes | client_task | Finding label/entry boxes on page images is visual generation. |
| check-boxes | execution | forms.md Step 3 automated check + Step 2 validation images. |
| boxes-gate | router | "iterate until there are no remaining errors." |
| inspect-boxes | decision (noul) | forms.md's manual image inspection has a fixed yes/no answer with written criteria (red only on blank areas, centered on squares, blue on labels). Threshold 0.3: a wrong placement is costly. |
| fill-annotations | execution | forms.md Step 4. |
| verify-output | execution | Read-back is deterministic: lists what is actually in the file with labels, intended-vs-actual mismatches, still-empty filer fields; renders the filled pages. |
| review-output | decision (noul) | "Is the PDF complete and correct against the facts?" is a yes/no judgment with explicit criteria; it gates the loop back. Threshold 0.25. |
| review-gate / fix-route | routers | Send corrections to whichever path produced the PDF. |

## Where each source item lives

| Source item | Location in the pack |
|---|---|
| forms.md "CRITICAL: complete these steps in order" | graph ordering; every write is behind a validation gate |
| forms.md check fillable fields first | inspect-form `is_fillable` + route-by-form-type |
| forms.md field_info JSON format (text/checkbox/radio_group/choice, checked/unchecked values, radio_options, choice_options) | `scripts/pdf_forms.py:get_field_info`, returned as `form_fields` |
| forms.md convert to PNGs and analyze images; convert PDF bbox coords to image coords | inspect-form `page_images`; map-fields template (coordinate formula) |
| forms.md field_values.json format; checkbox uses checked_value; radio uses a radio_options value | map-fields template items 4 and output; fill_fields.py validation |
| forms.md fill script validates IDs/values; fix and retry | fill_fields.py (same error messages) + fill-gate loop |
| forms.md non-fillable steps 1–4 ("follow exactly", all required) | locate-boxes → check-boxes → boxes-gate → inspect-boxes → boxes-visual-gate → fill-annotations |
| forms.md label/entry boxes must not intersect; entry only the data area, usually beside/above/below the label; tall and wide enough | locate-boxes template step 1; check_boxes.py |
| forms.md layout examples (label inside box, before line, under line, above line, checkboxes target the square) | locate-boxes template step 2 |
| forms.md fields.json format incl. font_size/font_color defaults | `assets/fields-format.md` (injected into locate-boxes) |
| forms.md validation images red/blue | check_boxes.py (`draw_validation_image`) |
| forms.md automated intersection + height check | `pdf_forms.bounding_box_messages` (passes the original `check_bounding_boxes_test.py`, all 10 cases) |
| forms.md manual inspection criteria | inspect-boxes `boxes_accurate` criteria |
| forms.md "repeat until fully accurate" | boxes-gate / boxes-visual-gate loops |
| forms.md add annotations | fill_annotations.py (same image→PDF transform, FreeText, Arial 14pt 000000 defaults) |
| extract_form_field_info: `/Off` is the unchecked value; unexpected states warning; unlocated fields ignored; sort by page/y/x | `get_field_info` + inspect `inspect_warnings` |
| fill_fillable_fields: page-number check, NeedAppearances, pypdf `/Opt` list-box monkeypatch | `fill_fields.py`, `pdf_forms.write_filled`, `monkeypatch_pypdf_choice_bug` |
| fill_pdf_form_with_annotations: skip empty entry_text; font size/color unreliable across viewers | `write_annotations`; fields-format.md note |
| convert_pdf_to_images: 200 dpi, longest side ≤ 1000 px | `render_pages` (via `pdftoppm`; pdf2image is not in the container) |
| SKILL.md general operations (merge, split, metadata, rotate, pdfplumber text/tables, reportlab, pdftotext/qpdf/pdftk, OCR, watermark, image extraction, passwords, quick-reference table) | `references/pdf-operations.md` (verbatim body; container-availability note added; cross-links repointed) |
| reference.md (pypdfium2, pdf-lib, pdfjs-dist, poppler/qpdf advanced, pdfplumber advanced, reportlab tables, batch processing, cropping, performance tips, troubleshooting encrypted/corrupted PDFs, licenses) | `references/pdf-advanced.md` (verbatim) |
| LICENSE.txt | frontmatter `license`, file kept in `source/pdf/` |

## Added beyond the source (from the task environment)

- `assets/form-profiles.json` — SC-100 profile: a label and `who` (filer / optional / clerk / court / never) for all 103 fields, notes, and machine-checked rules (exclusive groups, same-value header, currency, amount threshold, amount limit, requires/forbids, required core fields).
- `references/sc100-guide.md` — item-by-item SC-100 guidance, venue choices, limits, gotchas.
- Writing strips `/XFA` and `/Perms` from the output so viewers show the AcroForm values (otherwise Acrobat renders the blank XFA layer or flags broken usage rights).
- Pushbuttons are typed `pushbutton` and can never be set.
- Checkbox values tolerate `true`/`"Yes"`/`"X"` and normalize to the checked value (reported in `auto_changes`).
- Scripts resolve relative paths, accept the AIP stdin payload, and keep a CLI mode mirroring the original scripts' arguments.

## Deliberate-drop log

| Dropped | Rationale |
|---|---|
| `check_bounding_boxes_test.py` as a runtime step | It is a developer unit test ("not run automatically in CI; just for documentation"). Kept in `source/pdf/scripts/`; used once at authoring time to confirm the port behaves identically. |
| The original `python scripts/<name>.py` command lines | Replaced by execution steps that take the same inputs from the state; CLI mode is kept in each pack script for manual use. |
| `pdf2image` dependency in `convert_pdf_to_images.py` | Not installed in the task container; same output produced with `pdftoppm` + Pillow. |
| reference.md "pdf-lib maintains form structure better than most alternatives" as the default | The container has no Node.js/pdf-lib; pypdf is the installed, validated path. The tip stays in `references/pdf-advanced.md`. |
| extract_form_field_info's macOS Preview radio-button display note | Viewer trivia with no action for the agent. |
| Original SKILL.md frontmatter description wording ("When Claude needs to...") | Rewritten as this skill's description; general-toolkit scope now lives in references. |
