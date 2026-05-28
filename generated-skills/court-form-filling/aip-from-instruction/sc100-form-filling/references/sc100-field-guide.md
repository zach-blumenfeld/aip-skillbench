# SC-100 Field Guide

Reference for mapping a plain-English case description to fields on the
California Judicial Council's `SC-100` form ("Plaintiff's Claim and
ORDER to Go to Small Claims Court"). PDF field names vary slightly by
revision (10/2024, 09/2018, etc.) — always run `inspect_pdf_form.py`
first to get the exact names. The semantic layout below is stable across
revisions.

## Sections

### Section 1 — The Plaintiff (you suing)

- Plaintiff's name (individual or business). For natural persons, use
  the legal name from the case description.
- Mailing address: street, city, state, ZIP.
- Phone number.
- Email (optional on the form, but fill if present in the case description).

If the plaintiff is suing on behalf of a business / DBA, separate fields
appear for the entity name. Leave blank unless the case description
mentions a business.

### Section 2 — The Defendant (the person being sued)

- Defendant's name.
- Mailing address (or last known residence/business address).
- Phone number.

The form usually has space for multiple defendants (Defendant 2,
Defendant 3, …). Leave those blank when only one defendant is named.

### Section 3 — The claim

- "The Defendant owes me the sum of $______ not including court costs"
  → write the dollar amount as digits, no `$`, no commas (e.g.,
  `1500.00` or `1500`).
- "Why does the Defendant owe the Plaintiff money?" → one or two
  sentence narrative drawn from the case description. Be specific and
  factual: who, what was owed, what contract/agreement governs it.
- "When did this happen?" / date(s) of incident — use the date format
  required by the surrounding instruction. The task instruction may
  specify `xxxx-xx-xx` (ISO `YYYY-MM-DD`); follow that even though the
  form's printed example may show `MM/DD/YYYY`.

### Section 4 — Have you asked the Defendant to pay?

- Usually a "Yes / No" pair of checkboxes. If the case description
  indicates the plaintiff asked for payment (texts, calls, emails),
  check "Yes."
- If "No," there is a follow-up reason field — leave blank when the
  case description does not provide a reason.

### Section 5 — Why are you filing your claim here? (Venue)

A list of mutually exclusive checkboxes. Common options:

1. Where the Defendant lives or does business.
2. Where the injury or damage happened.
3. Where the contract was signed or carried out.
4. Where the buyer (consumer/retail) signed the contract.
5. Where a retail installment account or sales contract is.
6. Where the vehicle is garaged (vehicle finance suits).

For a security-deposit / sublease case where both parties live in the
same city and the plaintiff explicitly chose to file where the
**defendant lives**, check option (1) only. Leave the other reasons
blank.

### Section 6 — Other small-claims filings

Two checkboxes (or one with two sub-options):

- "I have filed 12 or fewer other small claims actions in California
  within the last 12 months."  → first-time / occasional filers check this.
- "I have filed more than 12 other small claims actions in California
  within the last 12 months." → only check this for frequent filers.

The case description's "first time suing by small claims" maps to the
≤12 box.

There may also be a checkbox stating that the claim is for $2,500 or
less and filed by an entity / sole proprietorship — leave blank unless
explicitly the case (it isn't, for this task).

### Section 7 — Understanding the rules

Some revisions include checkboxes acknowledging that the plaintiff
understands they cannot bring an attorney to small claims court. Treat
as "court informational" — only check if the form clearly requires the
plaintiff to attest, and the case description authorizes the attestation
(an instruction like "I understand the rules" or "file this for me as
plaintiff" is sufficient).

### Section 8 — Date and Signature

- "Date" — the filing date supplied in the case description, in the
  required format.
- "Plaintiff's signature" — leave the typed signature field blank.
  The plaintiff signs the printed form. Do not type a name in the
  signature box.
- "Type or print your name" — fill with the plaintiff's name.

## Court-Filled Fields — LEAVE BLANK

Never write to these. They are filled by the court clerk:

- Case Number (`Case No.` at the top of every page).
- "Fill in court name and street address" stamp — sometimes a fillable
  block; if not pre-printed, leave blank unless the case description
  names a specific courthouse.
- Filing date stamp ("Clerk stamps date here when form is filed").
- Hearing date / time / department (Order section, usually page 2).
- Fee amount / fee waiver disposition (the clerk fills based on FW-001
  if a fee waiver is filed).
- Server / Proof of Service blocks (these belong on a separate SC-104
  series form, not SC-100).

## Common Gotchas

- **Field-name inconsistency.** PDF field names on SC-100 are
  auto-generated (`PlaintiffName_1`, `Address`, `Topmostsubform[0]...`).
  Always run `inspect_pdf_form.py` first; do not assume names.
- **Checkbox values.** AcroForm checkboxes commonly use `/Yes` and
  `/Off` as appearance states. `fill_pdf_form.py` accepts either `Yes`
  or `/Yes` and normalizes. To leave a checkbox unchecked, omit the
  key from the mapping or set its value to `""`.
- **Multi-page repeated fields.** The Plaintiff name appears in the
  header of multiple pages (case caption). Fill every instance with
  the same name, otherwise the header on page 2/3 will look blank.
- **Don't invent data.** Court name, hearing date, case number, judge
  name — never fabricate. Leave blank if not in the case description.
- **Amount.** Write digits only, no `$`, no commas. Decimals optional
  (e.g., `1500` and `1500.00` are both acceptable).
- **Date format.** Follow the task instruction's stated format
  (commonly `YYYY-MM-DD`) even if it conflicts with the printed
  example on the form. The instruction supersedes the form's hint.
- **Plaintiff narrative ("why owed").** Keep it factual and short.
  Reference the contract / agreement, the amount, the dates, and the
  failure-to-pay. Avoid speculation about defendant's motivation.
