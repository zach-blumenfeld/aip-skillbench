#!/usr/bin/env python3
"""Build field_values.json for California form SC-100 (Plaintiff's Claim and ORDER to
Go to Small Claims Court) from a structured case.json.

Applies the SC-100 filling rules deterministically (which box answers which item,
item 10 from the claim amount, single date vs. date range, mirrored captions, fields
the plaintiff must never fill) and resolves every field ID and checkbox value against
the actual PDF, so a revised form fails loudly instead of filling the wrong box.

Requires: Python >= 3.10, pypdf >= 5.1 (+ cryptography for the encrypted court PDF).
Imports scripts/pdf_forms.py from the same folder.

Usage (run from the skill root):
  python3 scripts/sc100_build.py <blank_sc100.pdf> <case.json> <field_values.json> \
      [--date-format %Y-%m-%d] [--amount-style plain|comma|cents]
Then: python3 scripts/pdf_forms.py fill <blank.pdf> <field_values.json> <out.pdf>
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True
from pdf_forms import get_field_info, open_reader  # noqa: E402

P1 = "SC-100[0].Page1[0]."
P2 = "SC-100[0].Page2[0]."
P3 = "SC-100[0].Page3[0]."
P4 = "SC-100[0].Page4[0]."
PL = P2 + "List1[0].Item1[0]."
DF = P2 + "List2[0].item2[0]."

REQUIRED = ["plaintiffs", "defendants", "claim_amount", "why_owed", "how_calculated", "asked_to_pay",
            "venue", "attorney_fee_dispute", "public_entity", "more_than_12_claims", "filing_date"]

DATE_FORMATS = ["%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%B %d, %Y", "%B %d %Y",
                "%b %d, %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y", "%B %Y"]


class BuildError(Exception):
    pass


def norm_date(value, fmt, label):
    if value in (None, ""):
        return None
    s = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", str(value).strip())
    s = re.sub(r"\bSept\b", "Sep", s, flags=re.I)
    s = re.sub(r"\s+", " ", s)
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f).strftime(fmt)
        except ValueError:
            continue
    raise BuildError(f"{label}: cannot parse date {value!r}; give it as YYYY-MM-DD")


def norm_amount(value, style):
    s = str(value).replace("$", "").replace(",", "").strip()
    try:
        num = float(s)
    except ValueError:
        raise BuildError(f"claim_amount: {value!r} is not a number")
    if style == "cents":
        text = f"{num:.2f}"
    elif style == "comma":
        text = f"{num:,.2f}" if num != int(num) else f"{int(num):,}"
    else:
        text = str(int(num)) if num == int(num) else f"{num:.2f}"
    return text, num


def text(v):
    return "" if v is None else str(v).strip()


def build(case, info, date_fmt, amount_style):
    missing = [k for k in REQUIRED if k not in case or case[k] in (None, "", [])]
    if not (case.get("incident_date") or case.get("period_start")):
        missing.append("incident_date or period_start/period_end")
    if missing:
        raise BuildError("case.json is missing required keys: " + ", ".join(missing))

    by_id = {f["field_id"]: f for f in info}
    values = []  # (field_id, value, description)
    notes = []

    def put(fid, value, desc):
        if value in (None, ""):
            return
        if fid not in by_id:
            raise BuildError(f"field `{fid}` ({desc}) is not in this PDF; the SC-100 revision differs. "
                             "Fill this item via the generic fillable-form path.")
        values.append((fid, value, desc))

    def check(fid, desc):
        f = by_id.get(fid)
        if not f or "checked_value" not in f:
            raise BuildError(f"checkbox `{fid}` ({desc}) not found or has no checked value in this PDF")
        put(fid, f["checked_value"], desc)

    def yes_no(base, answer, item):
        check(f"{base}[0]" if answer else f"{base}[1]", f"Item {item}: {'Yes' if answer else 'No'}")

    # ---- item 1: plaintiffs (two slots on the form; more -> SC-100A)
    plaintiffs = case["plaintiffs"]
    names = [text(p.get("name")) for p in plaintiffs]
    caption = ", ".join(n for n in names if n)
    put(P2 + "PxCaption[0].Plaintiff[0]", caption, "Caption: plaintiff names (page 2)")
    # Pages 3-4 captions are read-only mirrors of page 2 in the form's XFA logic.
    put(P3 + "PxCaption[0].Plaintiff[0]", caption, "Caption: plaintiff names (page 3 mirror)")
    put(P4 + "PxCaption[0].Plaintiff[0]", caption, "Caption: plaintiff names (page 4 mirror)")
    for i, p in enumerate(plaintiffs[:2], start=1):
        put(f"{PL}PlaintiffName{i}[0]", text(p.get("name")), f"Item 1: plaintiff {i} name")
        put(f"{PL}PlaintiffPhone{i}[0]", text(p.get("phone")), f"Item 1: plaintiff {i} phone")
        put(f"{PL}PlaintiffAddress{i}[0]", text(p.get("street")), f"Item 1: plaintiff {i} street")
        put(f"{PL}PlaintiffCity{i}[0]", text(p.get("city")), f"Item 1: plaintiff {i} city")
        put(f"{PL}PlaintiffState{i}[0]", text(p.get("state")), f"Item 1: plaintiff {i} state")
        put(f"{PL}PlaintiffZip{i}[0]", text(p.get("zip")), f"Item 1: plaintiff {i} zip")
        m = p.get("mailing") or {}
        if text(m.get("street")) and text(m.get("street")).lower() != text(p.get("street")).lower():
            put(f"{PL}PlaintiffMailingAddress{i}[0]", text(m.get("street")), f"Item 1: plaintiff {i} mailing street")
            put(f"{PL}PlaintiffMailingCity{i}[0]", text(m.get("city")), f"Item 1: plaintiff {i} mailing city")
            put(f"{PL}PlaintiffMailingState{i}[0]", text(m.get("state")), f"Item 1: plaintiff {i} mailing state")
            put(f"{PL}PlaintiffMailingZip{i}[0]", text(m.get("zip")), f"Item 1: plaintiff {i} mailing zip")
        put(f"{PL}EmailAdd{i}[0]", text(p.get("email")), f"Item 1: plaintiff {i} email")
    if len(plaintiffs) > 2:
        check(PL + "Checkbox1[0]", "Item 1: more than two plaintiffs (attach SC-100A)")
        notes.append("More than two plaintiffs: list plaintiffs 3+ on form SC-100A.")
    if case.get("plaintiff_fictitious_business"):
        check(PL + "Checkbox2[0]", "Item 1: fictitious business name (attach SC-103)")
        notes.append("Attach form SC-103 (fictitious business name).")
    if case.get("plaintiff_payday_lender"):
        check(PL + "Checkbox3[0]", "Item 1: plaintiff is a licensee / deferred deposit originator")

    # ---- item 2: defendant (one slot; more -> SC-100A)
    defendants = case["defendants"]
    d = defendants[0]
    put(DF + "DefendantName1[0]", text(d.get("name")), "Item 2: defendant name")
    put(DF + "DefendantPhone1[0]", text(d.get("phone")), "Item 2: defendant phone")
    put(DF + "DefendantAddress1[0]", text(d.get("street")), "Item 2: defendant street")
    put(DF + "DefendantCity1[0]", text(d.get("city")), "Item 2: defendant city")
    put(DF + "DefendantState1[0]", text(d.get("state")), "Item 2: defendant state")
    put(DF + "DefendantZip1[0]", text(d.get("zip")), "Item 2: defendant zip")
    m = d.get("mailing") or {}
    if text(m.get("street")) and text(m.get("street")).lower() != text(d.get("street")).lower():
        put(DF + "DefendantMailingAddress1[0]", text(m.get("street")), "Item 2: defendant mailing street")
        put(DF + "DefendantMailingCity1[0]", text(m.get("city")), "Item 2: defendant mailing city")
        put(DF + "DefendantMailingState1[0]", text(m.get("state")), "Item 2: defendant mailing state")
        put(DF + "DefendantMailingZip1[0]", text(m.get("zip")), "Item 2: defendant mailing zip")
    agent = d.get("agent") or {}
    if text(agent.get("name")):
        put(DF + "DefendantName2[0]", text(agent.get("name")), "Item 2: agent for service name")
        put(DF + "DefendantJob1[0]", text(agent.get("job_title")), "Item 2: agent job title")
        put(DF + "DefendantAddress2[0]", text(agent.get("street")), "Item 2: agent street")
        put(DF + "DefendantCity2[0]", text(agent.get("city")), "Item 2: agent city")
        put(DF + "DefendantState2[0]", text(agent.get("state")), "Item 2: agent state")
        put(DF + "DefendantZip2[0]", text(agent.get("zip")), "Item 2: agent zip")
    if len(defendants) > 1:
        check(DF + "Checkbox4[0]", "Item 2: more than one defendant (attach SC-100A)")
        notes.append("More than one defendant: list defendants 2+ on form SC-100A.")
    if case.get("defendant_military"):
        check(DF + "Checkbox5[0]", "Item 2: a defendant is on active military duty")
        notes.append("The form has no fillable box for the military defendant's name; write it by hand after the checkbox.")

    # ---- item 3: claim
    amount_text, amount = norm_amount(case["claim_amount"], amount_style)
    put(P2 + "List3[0].PlaintiffClaimAmount1[0]", amount_text, "Item 3: amount claimed ($ is printed)")
    why = text(case["why_owed"])
    put(P2 + "List3[0].Lia[0].FillField2[0]", why, "Item 3a: why the defendant owes the money")
    single = norm_date(case.get("incident_date"), date_fmt, "incident_date")
    start = norm_date(case.get("period_start"), date_fmt, "period_start")
    end = norm_date(case.get("period_end"), date_fmt, "period_end")
    if start and end and start == end and not single:
        single, start, end = start, None, None
    if single:
        put(P3 + "List3[0].Lib[0].Date1[0]", single, "Item 3b: date it happened")
    else:
        if not end:
            raise BuildError("period_start given without period_end (or give incident_date)")
        put(P3 + "List3[0].Lib[0].Date2[0]", start, "Item 3b: date started")
        put(P3 + "List3[0].Lib[0].Date3[0]", end, "Item 3b: through")
    how = text(case["how_calculated"])
    put(P3 + "List3[0].Lic[0].FillField1[0]", how, "Item 3c: how the amount was calculated")
    if len(why) > 500 or len(how) > 350:
        notes.append("3a/3c text is long and may overflow its box; consider shortening or set need_more_space.")
    if case.get("need_more_space"):
        check(P3 + "List3[0].Checkbox1[0]", "Item 3: need more space (attach MC-031)")
        notes.append('Attach one sheet or form MC-031 titled "SC-100, Item 3".')

    # ---- item 4: asked defendant to pay
    asked = bool(case["asked_to_pay"])
    yes_no(P3 + "List4[0].Item4[0].Checkbox50", asked, 4)
    if not asked:
        if not text(case.get("why_not_asked")):
            raise BuildError("asked_to_pay is false: why_not_asked is required (item 4 explanation)")
        put(P3 + "List4[0].Item4[0].FillField2[0]", text(case["why_not_asked"]), "Item 4: why not asked")

    # ---- item 5: venue
    venue = text(case["venue"]).lower()
    letters = {"a": "Lia", "b": "Lib", "c": "Lic", "d": "Lid", "e": "Lie"}
    if venue not in letters:
        raise BuildError(f"venue must be one of a, b, c, d, e; got {venue!r}")
    check(f"{P3}List5[0].{letters[venue]}[0].Checkbox5cb[0]", f"Item 5{venue}: venue basis")
    if venue == "e":
        if not text(case.get("venue_other")):
            raise BuildError("venue 'e' requires venue_other (specify)")
        put(P3 + "List5[0].Lie[0].FillField55[0]", text(case["venue_other"]), "Item 5e: other (specify)")

    # ---- item 6: zip of the place in 5 (only if known)
    put(P3 + "List6[0].item6[0].ZipCode1[0]", text(case.get("venue_zip")), "Item 6: zip code of venue place")

    # ---- item 7: attorney-client fee dispute
    fee = bool(case["attorney_fee_dispute"])
    yes_no(P3 + "List7[0].item7[0].Checkbox60", fee, 7)
    if fee and case.get("had_arbitration"):
        check(P3 + "List7[0].item7[0].Checkbox11[0]", "Item 7: had arbitration (attach SC-101)")
        notes.append("Attach form SC-101 (attorney fee dispute after arbitration).")

    # ---- item 8: public entity
    public = bool(case["public_entity"])
    yes_no(P3 + "List8[0].item8[0].Checkbox61", public, 8)
    if public:
        filed = norm_date(case.get("public_claim_filed_date"), date_fmt, "public_claim_filed_date")
        if filed:
            check(P3 + "List8[0].item8[0].Checkbox14[0]", "Item 8: a claim was filed with the entity")
            put(P3 + "List8[0].item8[0].Date4[0]", filed, "Item 8: date the claim was filed")
        else:
            notes.append("Suing a public entity requires filing a written claim with it first; no filed date given.")

    # ---- item 9: more than 12 claims in 12 months
    yes_no(P4 + "List9[0].Item9[0].Checkbox62", bool(case["more_than_12_claims"]), 9)

    # ---- item 10: computed from the amount
    yes_no(P4 + "List10[0].li10[0].Checkbox63", amount > 2500, 10)
    if amount > 6250:
        notes.append("Large claim: confirm it is within the plaintiff's small-claims limit (lower for businesses than for individuals; see form SC-100-INFO).")

    # ---- signature block (item 11 has no field)
    filing = norm_date(case["filing_date"], date_fmt, "filing_date")
    put(P4 + "Sign[0].Date1[0]", filing, "Signature: date")
    put(P4 + "Sign[0].PlaintiffName1[0]", names[0], "Signature: plaintiff printed name")
    if len(plaintiffs) > 1:
        put(P4 + "Sign[0].Date2[0]", filing, "Signature: second plaintiff date")
        put(P4 + "Sign[0].PlaintiffName2[0]", names[1], "Signature: second plaintiff printed name")

    # ---- page 1 court box: only when the case statement names it
    put(P1 + "CaptionRight[0].County[0].CourtInfo[0]", text(case.get("court_name_address")), "Page 1: court name and street address")
    put(P1 + "CaptionRight[0].CN[0].CaseName[0]", text(case.get("case_name")), "Page 1: case name")

    out = [{"field_id": fid, "description": desc, "page": by_id[fid]["page"], "value": v} for fid, v, desc in values]
    return out, notes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("case")
    ap.add_argument("out")
    ap.add_argument("--date-format", default="%Y-%m-%d", help="strftime format for every date (default %%Y-%%m-%%d)")
    ap.add_argument("--amount-style", choices=["plain", "comma", "cents"], default="plain",
                    help="plain: 1500 / 1500.50; comma: 1,500; cents: 1500.00")
    a = ap.parse_args()
    with open(a.case) as f:
        case = json.load(f)
    info = get_field_info(open_reader(a.pdf))
    if not any(f["field_id"].startswith("SC-100[0]") for f in info):
        sys.exit("ERROR: this PDF is not form SC-100; use the generic fillable-form path in SKILL.md")
    try:
        values, notes = build(case, info, a.date_format, a.amount_style)
    except BuildError as e:
        sys.exit(f"ERROR: {e}")
    with open(a.out, "w") as f:
        json.dump(values, f, indent=2, ensure_ascii=False)
    for v in values:
        shown = v["value"] if len(str(v["value"])) < 70 else str(v["value"])[:67] + "..."
        print(f"p{v['page']}  {v['description']:<48} {shown}")
    print(f"\nWrote {len(values)} field values to {a.out}")
    print("Left empty on purpose (court/clerk only): case numbers, trial date/time/department/address, "
          "clerk date/signature, page 5-6 advisor boxes, Print/Save/Reset buttons.")
    for n in notes:
        print("NOTE:", n)


if __name__ == "__main__":
    main()
