---
name: sc100-form-filling
description: Fill the California small claims court form SC-100 ("Plaintiff's Claim and ORDER to Go to Small Claims Court") from a plain-English case description. Use when the user supplies an SC-100 blank PDF and a case description and wants the form filled out, leaving court-filled and unmentioned fields blank. Covers field discovery, plaintiff/defendant mapping, venue selection, amount and date formatting, repeated case-caption fields, and verifying the output PDF.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.10+ and the `pypdf` library (pip install pypdf). Scripts assume the blank PDF has an AcroForm.
---

```yaml
purpose: >
  Fill the California Judicial Council SC-100 small claims complaint PDF
  from a plain-English case description, writing only the fields the
  description supports, leaving court-filled and unmentioned fields
  blank, and respecting the date format the surrounding task specifies
  (commonly YYYY-MM-DD). Produces a filled fillable PDF at the path
  the task requests.

trigger_when:
  - User asks to fill an SC-100 PDF (e.g., paths like sc100-blank.pdf, sc100-filled.pdf).
  - User supplies a small claims case description (plaintiff, defendant, amount owed, reason) and a blank California small claims form.
  - User mentions "Plaintiff's Claim and ORDER to Go to Small Claims Court" or California small claims filing.
  - User asks for help mapping case facts into AcroForm fields for SC-100.

do_not_use_when:
  - The form is a different California Judicial Council form (UD-100 unlawful detainer, SC-103 fictitious-name claim, SC-104 proof of service, etc.) — those have different field semantics.
  - The user wants legal advice or claim-merit analysis rather than form filling.
  - There is no fillable AcroForm in the PDF (a flattened scan needs OCR + overlay, not this skill).

scope_and_approval: >
  This skill writes a single output PDF to the path the user specifies.
  It never modifies the input PDF. It does not file with the court, pay
  fees, or transmit the form anywhere. If the case description omits
  data needed for a field, leave that field blank — do NOT invent
  values (case number, court name, hearing date, defendant address
  details, etc.). If a checkbox decision is ambiguous from the case
  description, ask the user before checking it.

steps:
  - name: read-input
    description: >
      Read the case description carefully and extract a structured record:
      plaintiff (name, address, city, state, ZIP, phone, email), defendant
      (name, address, phone), claim amount (digits only), claim narrative,
      incident date range, whether plaintiff asked for payment, venue
      basis (where defendant lives / where contract performed / etc.),
      first-time-filer status, and the filing date. Also note the exact
      input/output PDF paths and any required date format from the
      instruction (commonly YYYY-MM-DD).

  - name: inspect-form
    description: >
      Run `python scripts/inspect_pdf_form.py <input.pdf> --json > fields.json`
      to enumerate every AcroForm field, its type (/Tx, /Btn, /Ch, /Sig),
      and for checkboxes the accepted appearance-state values (e.g., "/Yes").
      Field names on SC-100 are auto-generated and revision-specific, so
      do not assume names — always inspect first.

  - name: plan-mapping
    description: >
      Build a JSON mapping file `mapping.json` of {field_name -> value} by
      cross-referencing fields.json against the structured record from
      read-input and the section guide in `references/sc100-field-guide.md`.
      Rules - (a) Only include fields the case description supports.
      (b) For checkboxes, set the value to "Yes" to check, omit or "" to
      leave unchecked. (c) For amount, use digits only with no $ or commas.
      (d) For dates, use the format the instruction specified. (e) Fill
      the plaintiff name in EVERY case-caption header field (multi-page
      forms repeat it). (f) Leave court-filled fields (case number, court
      address, hearing date, fee, clerk stamp) blank. (g) Leave the
      signature field blank — only fill the typed-name and date fields.
    depends_on: [read-input, inspect-form]

  - name: validate-mapping
    description: >
      Sanity-check mapping.json before filling - every key must exist in
      fields.json (the inspect-form output); checkbox values must match
      one of the field's accepted appearance states; amount is purely
      numeric; dates match the required format; mutually exclusive venue
      checkboxes have at most one set. If validation fails, revise
      mapping.json and re-check.
    depends_on: [plan-mapping]

  - name: fill-form
    description: >
      Run `python scripts/fill_pdf_form.py <input.pdf> mapping.json <output.pdf>`.
      The script preserves the AcroForm and sets NeedAppearances=true so
      viewers regenerate visuals on open. It warns on stderr about any
      mapping keys that are not real fields — treat those warnings as
      errors and fix the mapping before reporting completion.
    depends_on: [validate-mapping]

  - name: verify-output
    description: >
      Run `python scripts/verify_filled.py <output.pdf> --expected mapping.json`
      to confirm every intended field is filled with the expected value
      and no other field was written. Exit code 0 means the filled PDF
      matches the plan. If a checkbox shows "/Off" where "/Yes" was
      expected, the form likely uses a non-standard appearance state —
      re-inspect that field's options and rerun fill-form.
    depends_on: [fill-form]

decisions:
  - signal: Case description says "first time suing by small claims" or "I have not filed other small claims cases."
    action: Check the "12 or fewer small claims actions in the last 12 months" box in Section 6. Leave the >12 box unchecked.
  - signal: Case description names a venue basis ("filing where defendant lives", "where the contract was signed", etc.).
    action: Check exactly one Section-5 venue checkbox matching that basis. Leave the other venue boxes blank.
  - signal: Case description says plaintiff asked for payment ("I have asked him to return the money multiple times via text").
    action: Check Section 4 "Yes" (asked Defendant to pay). Leave the "No" box and its follow-up reason field blank.
  - signal: Case description gives a date range (e.g., "from 2025-09-30 until 2026-01-19").
    action: Use the start date in the "when did this happen" / "from" field and the end date in the "to" / "until" field, formatted per the task's required format. If the form has only one date field, use the end date (when the harm crystallized).
  - signal: Field is one of case number, court name/address, hearing date, hearing time, department, clerk stamp, fee, fee-waiver disposition, or Proof of Service.
    action: Leave blank. These are court-filled.
  - signal: Field is the plaintiff signature field (/Sig type or labeled "Plaintiff's signature").
    action: Leave blank. Fill only the typed-name field and the date field next to it.
  - signal: Case description omits a value for which a field exists (e.g., defendant email, business DBA).
    action: Leave the field blank. Do not infer or fabricate.
  - signal: Instruction specifies a date format (e.g., "xxxx-xx-xx" meaning YYYY-MM-DD).
    action: Use that format for every date field, even when the form's printed example shows MM/DD/YYYY. The task instruction supersedes the form's hint.
  - signal: Plaintiff name appears in the case caption header on multiple pages.
    action: Fill every case-caption plaintiff-name field, not just the first one. Same for defendant name fields.

scenarios:
  - need: >
      Fill /root/sc100-blank.pdf to /root/sc100-filled.pdf for a single
      plaintiff suing a single defendant over an unreturned $1500
      security deposit on a signed sublease. Both parties live in the
      same California city; plaintiff is a first-time small claims
      filer; plaintiff asked defendant for payment via text; filing
      date supplied; dates in YYYY-MM-DD.
    context: >
      Inspecting the PDF reveals ~40 fields including PlaintiffName_*,
      PlaintiffAddress_*, DefendantName_*, DefendantAddress_*, Amount,
      ClaimNarrative, AskedDefendantYes (checkbox), VenueDefendantLives
      (checkbox), TwelveOrFewer (checkbox), Date, TypedPlaintiffName,
      plus court-filled CaseNumber, HearingDate, etc.
    action: >
      Map plaintiff fields (name, street, city, state=CA, ZIP, phone,
      email) into every header instance; map defendant fields (name,
      street, city, state=CA, ZIP, phone — leave email blank since not
      provided); set Amount="1500", ClaimNarrative summarizing the
      unreturned-security-deposit facts and the sublease contract,
      IncidentFrom="2025-09-30", IncidentTo="2026-01-19";
      check AskedDefendantYes; check VenueDefendantLives; check
      TwelveOrFewer; set Date="2026-01-19" and TypedPlaintiffName to
      the plaintiff's name; leave CaseNumber, HearingDate, fee fields,
      and the signature field blank. Run fill_pdf_form.py, then
      verify_filled.py.
    outcome: >
      /root/sc100-filled.pdf opens in a PDF viewer with all
      case-description-supported fields populated, court-filled fields
      blank, exactly one venue checkbox set, and the form still
      fillable (so the plaintiff can sign on paper before filing).

anti_patterns:
  - Fabricating a case number, hearing date, court name, or judge — these are clerk/court fields. Leave blank.
  - Typing a name into the plaintiff signature field. The signature is wet-signed on paper.
  - Writing the amount with "$" or commas ("$1,500.00"). Use plain digits ("1500" or "1500.00").
  - Using MM/DD/YYYY when the task instruction specified YYYY-MM-DD (or any other format). The instruction overrides the form's printed example.
  - Filling the plaintiff name only on page 1 and forgetting the page 2/3 case-caption headers. Multi-page forms repeat the caption.
  - Checking more than one venue checkbox in Section 5. The options are mutually exclusive.
  - Guessing field names instead of running inspect_pdf_form.py. Names are auto-generated and revision-specific.
  - Modifying the input PDF in place. Always write to the requested output path.
  - Inventing data the case description omits (defendant email, plaintiff DBA, etc.). Leave blank.
```
