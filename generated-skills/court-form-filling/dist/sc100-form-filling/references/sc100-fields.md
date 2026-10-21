# SC-100 field map (Rev. January 1, 2026 form, 6 pages, 103 fields)

Load when `sc100_build.py` reports a missing field (a different form revision), when you must
fill an SC-100 item by hand through the generic path, or when checking a filled PDF.
All IDs start with `SC-100[0].`; that prefix is omitted below. Checkbox checked value in
parentheses; unchecked is always `/Off`. **Who** = P (plaintiff fills when the facts exist),
C (court/clerk only — always leave empty), M (read-only mirror of the page-2 field).

| Item | Field ID (without `SC-100[0].`) | Meaning | Who |
|---|---|---|---|
| p1 | `Page1[0].CaptionRight[0].County[0].CourtInfo[0]` | "Superior Court of California, County of" + court street address | P, only if the case statement names the court |
| p1 | `Page1[0].CaptionRight[0].CN[0].CaseNumber[0]` | Case number | C |
| p1 | `Page1[0].CaptionRight[0].CN[0].CaseName[0]` | Case name | P, only if given |
| p1 | `Page1[0].Order[0].List1[0].LI1..LI3[0].TrialDate/TrialTime/TrialTIme3/TrialDepartment/TrialDateCourtAdd{n}[0]`, `...LI3[0].TrialDateClerkSignDate[0]`, `...TrialDateClerkSign[0]` | Order to Go to Court: trial dates, times, departments, court addresses, clerk date/signature | C |
| caption | `Page2[0].PxCaption[0].Plaintiff[0]` | "Plaintiff (list names)" | P |
| caption | `Page3[0].PxCaption[0].Plaintiff[0]`, `Page4[0].PxCaption[0].Plaintiff[0]` | same names | M (fill with the page-2 value) |
| caption | `Page2/3/4[0].PxCaption[0].CaseNumber[0]` | Case number | C |
| 1 | `Page2[0].List1[0].Item1[0].PlaintiffName1, PlaintiffPhone1, PlaintiffAddress1, PlaintiffCity1, PlaintiffState1, PlaintiffZip1 [0]` | Plaintiff 1 name, phone, street, city, state, zip | P |
| 1 | `...Item1[0].PlaintiffMailingAddress1, PlaintiffMailingCity1, PlaintiffMailingState1, PlaintiffMailingZip1 [0]` | Mailing address *if different* | P, only if different |
| 1 | `...Item1[0].EmailAdd1[0]` | Email (if available) | P |
| 1 | same names with `2` (e.g. `PlaintiffName2[0]`, `EmailAdd2[0]`) | Second plaintiff | P, only if there is one |
| 1 | `...Item1[0].Checkbox1[0]` (/1) | More than two plaintiffs → attach SC-100A | P |
| 1 | `...Item1[0].Checkbox2[0]` (/1) | A plaintiff does business under a fictitious name → attach SC-103 | P |
| 1 | `...Item1[0].Checkbox3[0]` (/1) | A plaintiff is a "licensee"/"deferred deposit originator" (payday lender) | P |
| 2 | `Page2[0].List2[0].item2[0].DefendantName1, DefendantPhone1, DefendantAddress1, DefendantCity1, DefendantState1, DefendantZip1 [0]` | Defendant | P |
| 2 | `...item2[0].DefendantMailingAddress1, DefendantMailingCity1, DefendantMailingState1, DefendantMailingZip1 [0]` | Defendant mailing address if different | P, only if different |
| 2 | `...item2[0].DefendantName2, DefendantJob1, DefendantAddress2, DefendantCity2, DefendantState2, DefendantZip2 [0]` | Agent for service of process (corporation, LLC, public entity) + job title | P, only for such defendants |
| 2 | `...item2[0].Checkbox4[0]` (/1) | More than one defendant → attach SC-100A | P |
| 2 | `...item2[0].Checkbox5[0]` (/1) | A defendant is on active military duty (no fillable name box) | P |
| 3 | `Page2[0].List3[0].PlaintiffClaimAmount1[0]` | Amount owed; `$` is pre-printed | P |
| 3a | `Page2[0].List3[0].Lia[0].FillField2[0]` | Why the defendant owes the money (multiline) | P |
| 3b | `Page3[0].List3[0].Lib[0].Date1[0]` | Specific date it happened | P (single date) |
| 3b | `Page3[0].List3[0].Lib[0].Date2[0]`, `...Date3[0]` | Date started / Through, when no specific date | P (period) |
| 3c | `Page3[0].List3[0].Lic[0].FillField1[0]` | How the amount was calculated (multiline) | P |
| 3 | `Page3[0].List3[0].Checkbox1[0]` (/1) | Need more space → attach MC-031 "SC-100, Item 3" | P |
| 4 | `Page3[0].List4[0].Item4[0].Checkbox50[0]` (/1) / `Checkbox50[1]` (/2) | Asked defendant to pay: Yes / No | P (exactly one) |
| 4 | `Page3[0].List4[0].Item4[0].FillField2[0]` | If no, why not | P, only if No |
| 5 | `Page3[0].List5[0].Lia[0].Checkbox5cb[0]` (/1) | a: (1) defendant lives/does business, (2) plaintiff's property damaged, (3) plaintiff injured, (4) contract made/signed/performed/broken or defendant lived/did business then — one box for all four | P (exactly one of a–e) |
| 5 | `...Lib[0].Checkbox5cb[0]` (/2) | b: buyer/lessee signed/lives/lived — consumer goods, services, loans (CCP § 395(b)) | P |
| 5 | `...Lic[0].Checkbox5cb[0]` (/3) | c: retail installment contract, e.g. credit card (Civ. Code § 1812.10) | P |
| 5 | `...Lid[0].Checkbox5cb[0]` (/4) | d: vehicle finance sale, or where vehicle permanently garaged (Civ. Code § 2984.4) | P |
| 5 | `...Lie[0].Checkbox5cb[0]` (/5) + `...Lie[0].FillField55[0]` | e: Other (specify) | P |
| 6 | `Page3[0].List6[0].item6[0].ZipCode1[0]` | Zip code of the place checked in 5 (if known) | P |
| 7 | `Page3[0].List7[0].item7[0].Checkbox60[0]` (/1) / `Checkbox60[1]` (/2) | Attorney-client fee dispute: Yes / No | P |
| 7 | `...item7[0].Checkbox11[0]` (/1) | Yes + had arbitration → attach SC-101 | P |
| 8 | `Page3[0].List8[0].item8[0].Checkbox61[0]` (/1) / `Checkbox61[1]` (/2) | Suing a public entity: Yes / No | P |
| 8 | `...item8[0].Checkbox14[0]` (/1) + `...item8[0].Date4[0]` | A claim was filed with the entity on (date) | P, only if Yes |
| 9 | `Page4[0].List9[0].Item9[0].Checkbox62[0]` (/1) / `Checkbox62[1]` (/2) | Filed more than 12 other small claims in CA in last 12 months: Yes / No | P |
| 10 | `Page4[0].List10[0].li10[0].Checkbox63[0]` (/1) / `Checkbox63[1]` (/2) | Claim for more than $2,500: Yes / No | P (computed) |
| 11 | — | "No right to appeal" acknowledgement: no field | — |
| sign | `Page4[0].Sign[0].Date1[0]`, `Page4[0].Sign[0].PlaintiffName1[0]` | Date + plaintiff printed name (signature itself is wet/e-signed, no field) | P |
| sign | `Page4[0].Sign[0].Date2[0]`, `...PlaintiffName2[0]` | Second plaintiff date + name | P, only if there is one |
| p5/p6 | `Page5[0].subRIght[0].NeedHelp[0].FillField1[0]`, `Page6[0].subRight[0].NeedHelpSpanish[0].FillField2[0]` | County small-claims advisor info | C |
| — | `#pageSet[0].MPLast[0].Print[0]`, `Save[0]`, `Reset[0]` | Push buttons | never |
