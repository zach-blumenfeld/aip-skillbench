# SC-100 (Plaintiff's Claim and ORDER to Go to Small Claims Court) — fill guide

California Judicial Council form, Rev. January 1, 2026, 6 pages, 103 AcroForm fields
(XFA/AcroForm hybrid, AES-encrypted with an empty user password). All field IDs start
with `SC-100[0].`; below they are shortened. The `label` and `who_fills` on each field
in `form_fields` come from `assets/form-profiles.json`, which the fill script also
enforces.

## Who fills what

| Area | Who | Fields |
|---|---|---|
| Page 1 court name + street address box | plaintiff | `Page1[0].CaptionRight[0].County[0].CourtInfo[0]` |
| Page 1 Case Number, page 2-4 header Case Number | clerk — leave blank | `...CN[0].CaseNumber[0]`, `PageN[0].PxCaption[0].CaseNumber[0]` |
| Page 1 Case Name | only if facts give/ask for it | `...CN[0].CaseName[0]` |
| Page 1 "Order to Go to Court" (trial date/time/department/address, clerk date + signature) | clerk — leave blank | `Page1[0].Order[0]...` |
| Pages 2-4 (items 1-11, declaration) | plaintiff | everything under `Page2/3/4` except CaseNumber |
| Pages 5-6 "Need help?" boxes | court — leave blank | `Page5...NeedHelp`, `Page6...NeedHelpSpanish` |
| Print / Save / Reset | never | `#pageSet[0].MPLast[0]...` |

## Item by item

- **Page 1 court box** — pre-printed "Superior Court of California, County of"; write the county, then the courthouse name and street address on the next line(s), as the facts give them. If facts give only the county, write the county.
- **Header "Plaintiff (list names)"** (pages 2, 3, 4) — all plaintiff names joined as written (e.g. "Aisha Rahman and Omar Rahman"), identical on each page (the fill script copies page 2's text to the others).
- **Item 1 plaintiff** — Name, Phone, Street address split into street / City / State / Zip. Mailing address only when the facts give a different one. Email if given. Second-plaintiff block only for a second plaintiff. A business plaintiff using a fictitious ("dba") name: check Checkbox2 (attach SC-103). More than two plaintiffs: Checkbox1. Payday lender/licensee plaintiff: Checkbox3.
- **Item 2 defendant** — same address split. If the defendant is a corporation, LLC, or public entity, the agent for service of process goes in `DefendantName2`/`DefendantJob1`/`DefendantAddress2...`; leave those blank for an individual. If the facts say the agent is "at the same address", repeat the defendant's street, city, state, and zip in the agent fields. A business name like "Acme Auto Repair" owned by a person: name the defendant as the facts name them. More than one defendant: Checkbox4. Defendant on active military duty: Checkbox5.
- **Item 3 amount** — `PlaintiffClaimAmount1`; "$" is printed, so write the figure only. Do not add court costs or service fees.
- **Item 3a** (`Page2...Lia[0].FillField2`) — why the defendant owes the money: what happened, who did what, the agreement/damage, dates, and that the defendant has not paid. Facts only.
- **Item 3b** — one date in `Date1`; or, when the facts give a span, `Date2` (started) and `Date3` (through).
- **Item 3c** (`Page3...Lic[0].FillField1`) — how the amount was calculated: itemize the components from the facts and show they sum to the item 3 amount (e.g. "Security deposit $1,500 minus $0 lawful deductions = $1,500" / "Repair estimate $850 + towing $150 = $1,000"). Court costs and service fees are excluded. Check `Page3...List3[0].Checkbox1` only if you actually need an attachment.
- **Item 4** — asked the defendant to pay before suing? Yes = `Checkbox50[0]` ("/1"), No = `Checkbox50[1]` ("/2"). If No, explain in `Item4[0].FillField2`. Demand letters, texts, emails, calls asking for payment all count as Yes.
- **Item 5** — why this courthouse; check exactly one:
  - a (`Lia...Checkbox5cb`, "/1"): defendant lives/does business here; plaintiff's property was damaged here; plaintiff was injured here; or a contract was made/signed/performed/broken here. The default for most disputes (landlord deposit, unpaid loan between people, property damage, unpaid services).
  - b ("/2"): consumer contract for personal/family/household goods, services, or loans, filed where the buyer/lessee signed, lives, or lived.
  - c ("/3"): retail installment contract (credit card).
  - d ("/4"): vehicle finance sale.
  - e ("/5") + `FillField55`: other — specify.
- **Item 6** (`ZipCode1`) — zip code of the place chosen in item 5 (e.g. where the defendant lives/does business, where the damage occurred, where the contract was made). Fill it whenever the facts give that address. If the facts state a zip for the venue place, use exactly that one.
- **Item 7** — attorney-client fee dispute? Yes `Checkbox60[0]` / No `Checkbox60[1]`. `Checkbox11` only if Yes and arbitration happened (attach SC-101).
- **Item 8** — suing a public entity (city, county, state agency, school district, transit district)? Yes `Checkbox61[0]` / No `Checkbox61[1]`. If Yes, a written claim must already have been filed: check `Checkbox14` and give the date in `Date4`. There is no field for the entity's denial date; mention it in the item 3a narrative. Public-entity defendants with no named agent: leave the agent-for-service fields blank.
- **Item 9** — filed more than 12 other small claims in California in the last 12 months? Yes `Checkbox62[0]` / No `Checkbox62[1]`. No unless the facts say otherwise. (Yes raises the filing fee.)
- **Item 10** — claim for more than $2,500? Yes `Checkbox63[0]` / No `Checkbox63[1]`. Determined by the item 3 amount (strictly greater than 2,500 = Yes); the fill script sets it and rejects a contradiction. Yes also confirms no more than two >$2,500 claims this calendar year.
- **Item 11** — acknowledgement that the plaintiff cannot appeal; no field.
- **Declaration** (page 4) — `Sign[0].Date1` and `Sign[0].PlaintiffName1` (printed name). Second plaintiff: `Date2`, `PlaintiffName2`. No signature field exists; never draw or type a signature into another field.

## Limits and rules worth checking against the facts

- Individuals and sole proprietors: up to $12,500. Corporations, partnerships, public entities, other businesses: up to $6,250 (exceptions for guarantors). The fill script warns above these.
- The plaintiff must ask the defendant for payment (or the property) before suing (item 4).
- Public entity defendants need a prior written claim (item 8).
- Serving: someone 18+ who is not a party serves each defendant (not a field; mention only if asked).

## Gotchas

- The blank file is encrypted (AES). pypdf needs the `cryptography` package; the container has it.
- It is an XFA hybrid with a Reader-extensions signature. The fill script removes `/XFA` and `/Perms` from the output so every viewer shows the AcroForm values instead of the blank XFA layer or a "document changed" rights error. Don't "fix" this by writing with another library.
- Yes/No answers are two checkboxes with on-values "/1" (Yes) and "/2" (No). Setting the "No" box to "/1" is invalid.
- Do not fill the clerk's Order section on page 1 even if the facts mention a hearing date — the clerk assigns it.
