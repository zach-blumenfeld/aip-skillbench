---
name: sc100-form-filling
description: Fill the California Small Claims form SC-100 (Plaintiff's Claim and ORDER to Go to Small Claims Court) from a plain-language case description, and fill other PDF court forms — fillable (AcroForm/XFA) or flat/scanned — with pypdf. Use when asked to complete, fill in, or prepare an SC-100 or similar court/government PDF form from case facts, leaving court-only and unmentioned fields empty and writing dates in a requested format.
license: Proprietary (derived from Anthropic's pdf skill). source/pdf/LICENSE.txt has complete terms
compatibility: Python >= 3.10; pip packages pypdf>=5.1, cryptography (opens the encrypted court PDF), Pillow (render, validation images), and for rendering one of pymupdf / pdf2image / poppler-utils `pdftoppm` (tried in that order). All present in the task container (pypdf 5.1.0 + cryptography; fillpdf pulls in pymupdf, pdf2image, Pillow; poppler-utils installed).
---

# SC-100 Small Claims Form Filling

## Trigger When

1. A task says to fill California form SC-100 / "Plaintiff's Claim and ORDER to Go to Small Claims Court" (e.g. `/root/sc100-blank.pdf`) from a case description.
2. A small-claims plaintiff describes who they are suing, for how much, and why, and wants the claim form prepared.
3. Any PDF form (court, government, intake) must be filled from free-text facts with only the necessary fields set.
4. A PDF form has no fillable fields and text must be placed visually.

## Purpose

Turns a case description into a correctly filled SC-100: it extracts the plaintiff/defendant/claim facts into a fixed `case.json`, answers the form's yes/no and venue questions as typed decisions, and lets a script apply the SC-100 rules (which checkbox answers which item, item 10 from the amount, single date vs. period, page-3/4 caption mirrors, court-only fields left blank) against the real field IDs before filling with pypdf. It also carries the general fillable and non-fillable PDF form workflows for forms other than SC-100.

## Before the first script

Check `python3 --version` (≥ 3.10) and `python3 -c "import pypdf, cryptography, PIL"`; for rendering also one of `python3 -c "import pymupdf"`, `python3 -c "import pdf2image"`, or `which pdftoppm`. Name everything missing before continuing. Run every command from this skill's root folder; write working files (case.json, field_values.json, images) to a scratch dir such as `/tmp/sc100/`, never into the skill folder.

## Workflow

- [ ] 1. Inspect the PDF (script)
- [ ] 2. Answer the case questions (decision)
- [ ] 3. Write `case.json` (client task)
- [ ] 4. Build and validate field values (script)
- [ ] 5. Fill (script)
- [ ] 6. Verify (script + look)

### 1. Inspect — `execution`

```bash
python3 scripts/pdf_forms.py check /root/sc100-blank.pdf
```
Prints JSON `{fillable, field_count, pages, encrypted, has_xfa, form_id}`. Branch:
- `form_id == "SC-100"` → continue with steps 2–6.
- `fillable: true`, other form → [Generic fillable form](#generic-fillable-form).
- `fillable: false` → follow [references/non-fillable-forms.md](references/non-fillable-forms.md).

### 2. Case questions — `decision`

Input: the case description. Answer all in one pass; reconsider any close call.

```yaml
venue:
  type: choice
  instructions: Which item-5 box says why the claim is filed at this courthouse? Use the plaintiff's stated reason first; if none is stated, pick what the facts support.
  criteria:
    a: Where the defendant lives or does business; where the plaintiff's property was damaged; where the plaintiff was injured; or where a contract was made, signed, performed, or broken by the defendant (or where the defendant lived/did business then). Ordinary person-to-person disputes, deposits, loans between individuals.
    b: Buyer or lessee's location, for an offer or contract for personal, family, or household goods, services, or loans (CCP 395(b)).
    c: Buyer's location, for a retail installment contract such as a credit card.
    d: Buyer's location or where the vehicle is garaged, for a vehicle finance sale.
    e: None of the above; requires venue_other text.
incident_timing:
  type: choice
  instructions: How does the description date the event for item 3b?
  criteria:
    single_date: One specific date ("on 2025-03-02") -> incident_date.
    period: A range ("from X until Y", "between", "since X through Y") -> period_start + period_end.
asked_to_pay:
  type: noul
  instructions: Did the plaintiff ask the defendant to pay (in person, in writing, text, or phone) before suing?
  criteria:
    true: Any request is described — calls, texts, letters, emails, even unanswered.
    false: The description says no request was made; then why_not_asked is required.
attorney_fee_dispute:
  type: noul
  instructions: Is the claim an attorney-client fee dispute?
  criteria:
    true: The money is a lawyer's fee the plaintiff (client or attorney) disputes.
    false: Anything else, including all landlord, deposit, loan, repair, and purchase disputes.
more_than_12_claims:
  type: noul
  instructions: Has the plaintiff filed more than 12 other small claims in California in the last 12 months?
  criteria:
    true: The description says so (frequent filer, collections business with many cases).
    false: '"First time suing", a small number of past claims, or no mention.'
public_entity:
  type: noul
  instructions: Is the defendant a public entity?
  criteria:
    true: City, county, state agency, school or transit district, other government body.
    false: Individuals and private businesses.
defendant_is_organization:
  type: noul
  instructions: Is the defendant an entity whose agent for service belongs in item 2?
  criteria:
    true: Corporation, LLC, or public entity.
    false: An individual (even one doing business as a sole proprietor).
plaintiff_fictitious_business:
  type: noul
  instructions: Does a plaintiff sue under a fictitious business name (DBA)?
  criteria:
    true: The plaintiff is a business operating under an assumed name.
    false: Individuals suing in their own name; no mention.
plaintiff_payday_lender:
  type: noul
  instructions: Is a plaintiff a licensee or deferred deposit originator (payday lender) under Financial Code 23000 et seq.?
  criteria:
    true: The description says the plaintiff is such a lender.
    false: Anything else; no mention.
defendant_military:
  type: noul
  instructions: Is a defendant on active military duty?
  criteria:
    true: The description says so.
    false: No mention, veterans, reservists not on active duty.
had_arbitration:
  type: noul
  instructions: Has attorney-fee arbitration already happened?
  criteria:
    true: attorney_fee_dispute is true and arbitration is described.
    false: Otherwise (always false when attorney_fee_dispute is false).
need_more_space:
  type: noul
  instructions: After drafting 3a/3c in step 3, do they need more than about 5 lines (3a) or 4 lines (3c)?
  criteria:
    true: Essential facts cannot be cut to fit; an MC-031 attachment will be added.
    false: The text fits (prefer shortening).
```

A false positive on any noul checks a box the plaintiff never claimed; when unsure and the description is silent, answer false. Item 10 (> $2,500) is not a question: the script computes it.

### 3. Write `case.json` — `client_task`

Copy [assets/case_template.json](assets/case_template.json) to the scratch dir and fill it from the description and step 2:

- Copy names, phones, emails, and street addresses **verbatim** (do not reformat `4125886066` into `(412) 588-6066`). Split each address into `street`, `city`, `state` (two letters), `zip`.
- `mailing`: `null` unless a different mailing address is given (object with street/city/state/zip).
- `agent` (only if `defendant_is_organization`): `{"name","job_title","street","city","state","zip"}` from the description, else `null`.
- `claim_amount`: the number as stated. Dates: any common format; the script normalises them.
- `why_owed` (3a) and `how_calculated` (3c): one or two plain factual sentences built only from the description — what the defendant did or failed to do, the agreement/document, and where the number comes from (e.g. "Security deposit of $1500 stated in the signed roommate sublease contract; no deductions."). Do not invent facts, court costs, or interest.
- `venue_zip`: the zip of the place behind the venue choice (e.g. the defendant's zip for "where defendant lives"); empty if unknown.
- `filing_date`: the date the user says to file/sign with.
- `court_name_address`, `case_name`: fill **only** if the description states them; otherwise `""`. Do not infer a county from a city.
- Several plaintiffs/defendants: list all; the script fills the first two plaintiffs / first defendant and checks the SC-100A boxes.

### 4. Build — `execution`

```bash
python3 scripts/sc100_build.py /root/sc100-blank.pdf /tmp/sc100/case.json /tmp/sc100/field_values.json --date-format %Y-%m-%d
```
Set `--date-format` to the task's requested format (`xxxx-xx-xx` → `%Y-%m-%d`, `mm/dd/yyyy` → `%m/%d/%Y`); default is `%Y-%m-%d`. `--amount-style plain|comma|cents` gives `1500` / `1,500` / `1500.00` (default `plain`, matching how amounts are usually stated).
It prints one line per field it will set plus `NOTE:` lines (attachments needed, overflow risk, large-claim limit check). Read the plan against the description; an `ERROR:` names the missing key or bad value — fix `case.json` and rerun. If it says a field is not in this PDF (a different form revision), load [references/sc100-fields.md](references/sc100-fields.md) and fill that item through the generic path.

### 5. Fill — `execution`

```bash
python3 scripts/pdf_forms.py fill /root/sc100-blank.pdf /tmp/sc100/field_values.json /root/sc100-filled.pdf
```
Validates every ID, page, and checkbox value before writing; on `ERROR:` nothing is written. It opens the encrypted source, writes an unencrypted copy, sets NeedAppearances, and drops the XFA layer (otherwise Acrobat shows the blank XFA form); `--keep-xfa` skips that. `NOTE: ... read-only` for the page-3/4 captions is expected.

### 6. Verify — `execution`

```bash
python3 scripts/pdf_forms.py dump /root/sc100-filled.pdf
```
Lists every non-empty field. Confirm: each value matches the description; exactly one of each Yes/No pair is set; no case number, trial, clerk, page-5/6, or second-plaintiff field appears unless warranted; dates use the requested format. Optionally `python3 scripts/pdf_forms.py render /root/sc100-filled.pdf /tmp/sc100/img` and look at pages 2–4 (renderers that ignore NeedAppearances may show blanks; trust `dump`).

## Generic fillable form

For fillable PDFs other than SC-100 (or SC-100 items the builder cannot map):
1. `python3 scripts/pdf_forms.py extract <in.pdf> /tmp/form/field_info.json` — list of `{field_id, page, rect [l,b,r,t] in PDF points (y=0 at bottom), type text|checkbox|radio_group|choice|pushbutton, checked_value/unchecked_value, radio_options[{value,rect}], choice_options[{value,text}], tooltip, read_only}`. The `tooltip` usually states the field's question.
2. `python3 scripts/pdf_forms.py render <in.pdf> /tmp/form/img` and match fields to labels (convert rects: image_x = x·W/page_width, image_y = (page_height − y)·H/page_height).
3. Write `field_values.json`: `[{"field_id": "...", "description": "...", "page": 1, "value": "..."}]`. Checkboxes take their `checked_value` (e.g. `/1`, `/On`); radio groups one of `radio_options[].value`; choices one of `choice_options[].value`. Never set push buttons; skip court-only and unmentioned fields.
4. `python3 scripts/pdf_forms.py fill <in.pdf> /tmp/form/field_values.json <out.pdf>`; fix any `ERROR:` and rerun; then `dump` to verify.

For non-form PDF work (extract text, merge, split, rotate, encrypt), read [references/pdf-general.md](references/pdf-general.md); it links [references/pdf-advanced.md](references/pdf-advanced.md).

## Gotchas

- "Only fill the necessary fields": leave empty the court-filled fields (case number everywhere, trial order block, clerk, page 5–6 advisor boxes), the second plaintiff block, mailing addresses that are not different, item-4 explanation when Yes, item-8 date when No, and the page-1 court/case-name box unless stated.
- Answer every Yes/No item (4, 7, 8, 9, 10) with exactly one box; "No" is a real answer, not an empty field.
- 3b is either the single date **or** started/through, never both.
- The `$` in item 3 is pre-printed; the value is the number only.
- Item 5a is one checkbox covering sub-reasons (1)–(4); there are no separate boxes.
- The SC-100 PDF is encrypted (empty password) and carries XFA; plain `PdfReader` works because `cryptography` is installed, but other tools (pdftk, qpdf) are not available.
