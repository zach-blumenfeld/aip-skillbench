# Source and provenance

## Inputs

`pdf/` is a verbatim copy of the curated skill this skill was compiled from (Anthropic `pdf` skill;
proprietary, see `pdf/LICENSE.txt`):

| File | Content |
|---|---|
| `pdf/SKILL.md` | General PDF toolkit: pypdf, pdfplumber, reportlab, poppler/qpdf/pdftk CLI, OCR, watermark, encryption |
| `pdf/forms.md` | Form-filling procedure: fillable path (extract → render → field_values.json → fill) and non-fillable path (render → fields.json → validation images → box check → annotate) |
| `pdf/reference.md` | Advanced reference: pypdfium2, pdf-lib, pdf.js, poppler/qpdf advanced, pdfplumber/reportlab advanced, batch/cropping, performance, troubleshooting |
| `pdf/scripts/*.py` | 7 helper scripts + 1 unit test (`check_bounding_boxes_test.py`) |

Task context used (not copied; it lives outside the skill): the task statement (fill
`/root/sc100-blank.pdf` from a case description into `/root/sc100-filled.pdf`, only necessary fields,
dates `xxxx-xx-xx`), the real SC-100 PDF (Rev. January 1, 2026; 6 pages, 103 leaf fields, encrypted
with an empty password, AcroForm + XFA), and the container Dockerfile (Ubuntu 24.04, python3,
poppler-utils, pypdf 5.1.0, fillpdf 0.7.3 → pdf2image/pymupdf/Pillow, pdfrw, PyPDF2, reportlab, cryptography).

## Intent

The downstream task is a specific instance of "fill a court PDF form from free-text facts". The
source skill gives a generic, mostly free-form procedure; an agent following it must still discover
the SC-100 field semantics from 103 cryptic XFA-style IDs, decide each yes/no item, and remember
which fields are court-only. This skill pre-computes that SC-100 knowledge (field map, rules) into a
script, turns the form's judgment questions into typed decisions, and keeps the generic fillable and
non-fillable workflows for any other form or revision.

## Component-kind choices

| Component | Kind | Why |
|---|---|---|
| Inspect PDF (`pdf_forms.py check`) | execution | Deterministic: fillable?, encrypted?, XFA?, SC-100 detection by field prefix. Its JSON drives the branch. |
| Case questions (venue, incident_timing, asked_to_pay, attorney_fee_dispute, more_than_12_claims, public_entity, defendant_is_organization, plaintiff_fictitious_business, plaintiff_payday_lender, defendant_military, had_arbitration, need_more_space) | decision | Each requires judging free text, but the answer space is fixed (form checkboxes): choice for item 5 and 3b, nouls for the rest. Defaults (false when silent) stated, since a false positive checks a box the plaintiff never claimed. |
| Write `case.json` | client_task | Verbatim extraction plus two short generated texts (3a, 3c); generation needs the agent. Constrained by a template asset and explicit rules (verbatim values, no inferred court/county). |
| Build values (`sc100_build.py`) | execution | All item→field mapping, checkbox selection, item 10 (> $2,500) threshold, single-date vs period rule, date normalisation, amount formatting, caption mirroring, mailing-only-if-different, SC-100A/SC-103/SC-101/MC-031 notes, and missing-input validation are deterministic rules over structured input. Field IDs and checked values are resolved against the actual PDF, so a revised form fails loudly. |
| Fill (`pdf_forms.py fill`) | execution | Source `fill_fillable_fields.py`, with validation kept, plus: empty-password decryption, push-button guard, text-type check, read-only note, XFA removal (Acrobat otherwise shows the blank XFA form). |
| Verify (`pdf_forms.py dump`, `render`) | execution + agent look | Dump is deterministic; final visual check of rendered pages is the source's "inspect" step. |
| Generic fillable path | execution + client_task | Scripts for extract/render/fill; mapping fields to facts is judgment over images/tooltips (client task). |
| Non-fillable path (`references/non-fillable-forms.md`) | execution + client_task | Bounding-box estimation from images must be done by the agent; checks, validation images, and annotation are scripts. Moved to a reference because SC-100 is fillable; loaded only when `check` says not fillable. |
| General PDF ops (`references/pdf-general.md`, `references/pdf-advanced.md`) | reference | Not part of the form workflow; kept verbatim for on-demand use, with a container-availability caveat prepended. |

Scripts were consolidated: the 7 source scripts became `scripts/pdf_forms.py` subcommands
(check, extract, render, fill, dump, check-boxes, validation-image, annotate); SC-100 rules are in
`scripts/sc100_build.py`.

## Changes to source script behaviour (all verified in the functional test)

- `extract`: adds `tooltip` (/TU — on SC-100 it states each field's question), `read_only`, and `pushbutton` type; fixes choice options given as plain strings (the source split `"CA"` into value `"C"`/text `"A"`); fixes the `${field_id}` typo in the checkbox warning.
- `render`: prefers PyMuPDF (draws filled checkboxes correctly; poppler without the form fonts showed none), then pdf2image (source), then the `pdftoppm` binary. DPI 200 and max side 1000 px kept.
- `fill`: decrypts empty-password PDFs; removes `/XFA` unless `--keep-xfa`; rejects push buttons and non-string text values; writes nothing on any error.
- `dump`: new; lists non-empty values (radio groups included) for verification.
- `check-boxes`: same messages and 20-message cap; now exits 1 on failure. The source unit test suite (`check_bounding_boxes_test.py`, 10 tests) passes against the new function.

## Completeness check (source → skill)

| Source item | Where in the skill |
|---|---|
| forms.md "complete steps in order; check fillable first" | SKILL.md Workflow checklist + step 1 branch |
| forms.md field_info.json format (field_id, page, rect, type, checked/unchecked, radio_options, choice_options) | SKILL.md Generic fillable form step 1 |
| forms.md render + analyse images, convert PDF→image coordinates | Generic step 2 (with formula) |
| forms.md field_values.json format; checkbox uses checked_value; radio uses radio_options value | Generic step 3; SC-100 path generates it in `sc100_build.py` |
| forms.md fill script validates IDs/values; fix and retry | SKILL.md steps 5 and Generic step 4; `cmd_fill` |
| forms.md non-fillable steps 1–4, box examples (label inside box / before line / under line / above line / checkboxes), fields.json format, font defaults, validation image colours, automated + manual checks, annotate | `references/non-fillable-forms.md`; `pdf_forms.py check-boxes / validation-image / annotate` |
| Script comments: /Off as unchecked value, radio annotations per option, Preview radio display caveat, fields without location ignored, NeedAppearances note, pypdf /Opt monkeypatch, FreeText font caveat | Preserved as comments/messages in `pdf_forms.py` |
| SKILL.md Overview/Quick Start/pypdf/pdfplumber/reportlab/CLI/OCR/watermark/images/password/Quick Reference/Next Steps | `references/pdf-general.md` (verbatim, pointers updated) |
| reference.md (all sections) | `references/pdf-advanced.md` (verbatim) |
| LICENSE.txt | kept in `source/pdf/`; referenced from frontmatter `license` |

## Deliberate drops

- `check_bounding_boxes_test.py` not shipped as a skill script: it is documentation-only unit tests ("not run automatically in CI"); behaviour is preserved and was verified by running the suite against the new code during authoring. The original remains in `source/pdf/scripts/`.
- Source SKILL.md frontmatter `description` wording ("Comprehensive PDF manipulation toolkit…"): replaced by an SC-100/form-filling description; the general toolkit stays reachable via `references/pdf-general.md`.
- "Run this script from this file's directory" phrasing: replaced by one rule (run from the skill root) with exact commands.
- No content of forms.md, reference.md, or the scripts' logic was dropped otherwise.

## SC-100 knowledge added (from the real form, not the source skill)

Field map with roles (`references/sc100-fields.md`), checkbox values (`/1`…`/5`), Yes/No pairs
(`[0]`=Yes, `[1]`=No), read-only page-3/4 caption mirrors, court-only fields, item-5a single box
for sub-reasons (1)–(4), item 11 and signatures have no fields, encryption + XFA. All derived from
the PDF's field dictionaries (/T, /TU, /Ff, /_States_) and rendered pages.
