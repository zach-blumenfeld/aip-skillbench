"""Step `build-sc100-values`: turn the extracted case facts and the decision answers
into SC-100 field values, deterministically.

stdin state: sc100_case (object), the decision answers (asked_before_suing,
venue_basis, attorney_fee_dispute, fee_arbitration_done, suing_public_entity,
over_12_claims, defendant_military, plaintiff_fictitious_name, plaintiff_payday_lender),
form_fields (from inspect-form), date_format.
assets: sc100_field_map.
stdout: {"sc100_field_values": [{field_id, page, value, slot}], "sc100_mapping_notes": [...]}

Rules encoded here (SC-100 Rev. 2026-01-01):
- Fill only what the case supplies; empty facts leave their field empty. Court/clerk
  fields (case number, case name, trial dates, clerk signature, help boxes) are never filled.
- The page 2-4 caption "Plaintiff (list names)" gets the plaintiff names.
- Mailing address only when it differs from the street address.
- Items 4, 7, 8, 9, 10 are yes/no questions the plaintiff must answer: exactly one box
  each. Item 10 (claim over $2,500) is computed from the amount, not judged.
- Item 3b: a specific date goes in "Date"; otherwise "Date started"/"Through".
- Item 5: check exactly one venue box (a-e); "other" also fills its specify line.
- Signature block: plaintiff 1 name + filing date; plaintiff 2 only if there is one.
- Dates are reformatted to `date_format` (e.g. YYYY-MM-DD); the amount is written as a
  plain number without "$" or thousands separators (the form prints "$").
- More than two plaintiffs / more than one defendant check the SC-100A boxes.
"""
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from pdf_form_lib import emit, fail, read_stdin

VENUE_SLOT = {
    "defendant_or_contract_or_injury": "cb_venue_a",
    "consumer_contract": "cb_venue_b",
    "retail_installment": "cb_venue_c",
    "vehicle_finance": "cb_venue_d",
    "other": "cb_venue_e",
}

DATE_INPUT_FORMATS = [
    "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y",
    "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y", "%b. %d, %Y",
    "%d %B %Y", "%d %b %Y", "%B %dst, %Y", "%B %dnd, %Y", "%B %drd, %Y", "%B %dth, %Y",
]


def strftime_pattern(date_format):
    fmt = (date_format or "YYYY-MM-DD").strip()
    if re.fullmatch(r"[xX]{4}-[xX]{2}-[xX]{2}", fmt):
        fmt = "YYYY-MM-DD"
    out = fmt.replace("YYYY", "%Y").replace("yyyy", "%Y").replace("MM", "%m").replace("DD", "%d").replace("dd", "%d")
    if "%Y" not in out or "%m" not in out or "%d" not in out:
        fail(f"Unsupported date_format {date_format!r}; use tokens YYYY, MM, DD (e.g. YYYY-MM-DD, MM/DD/YYYY).")
    return out


def fmt_date(value, pattern, what):
    if value in (None, ""):
        return ""
    text = " ".join(str(value).replace(",", ", ").split()).replace(" ,", ",")
    for f in DATE_INPUT_FORMATS:
        try:
            return datetime.strptime(text, f).strftime(pattern)
        except ValueError:
            continue
    fail(f"Cannot parse {what} date {value!r}; give it as YYYY-MM-DD in sc100_case.")


def fmt_amount(value):
    if value in (None, ""):
        return "", None
    text = re.sub(r"[,$\s]", "", str(value))
    try:
        amt = Decimal(text)
    except InvalidOperation:
        fail(f"Cannot parse claim_amount {value!r}; give a number such as 1500 or 1500.50.")
    s = str(amt.quantize(Decimal(1))) if amt == amt.to_integral_value() else f"{amt:.2f}"
    return s, amt


def s(v):
    return "" if v is None else str(v).strip()


def main():
    payload = read_stdin()
    st = payload.get("state", {})
    raw_map = payload.get("assets", {}).get("sc100_field_map")
    fmap = json.loads(raw_map) if isinstance(raw_map, str) else raw_map
    if fmap is None:
        with open("../assets/sc100_field_map.json") as f:
            fmap = json.load(f)

    fields = {f["field_id"]: f for f in st["form_fields"]}
    slot_field = {}
    for slot, sfx in fmap["fields"].items():
        hits = [fid for fid in fields if fid == sfx or fid.endswith("." + sfx)]
        if len(hits) != 1:
            fail(f"Field-map slot {slot} ({sfx}) matched {len(hits)} fields; this form revision needs the generic route.")
        slot_field[slot] = hits[0]

    case = st["sc100_case"]
    pattern = strftime_pattern(st.get("date_format"))
    notes = []
    values = {}

    def put(slot, value):
        value = s(value)
        if value:
            values[slot] = value

    def check(slot):
        values[slot] = fields[slot_field[slot]].get("checked_value") or "/1"

    plaintiffs = [p for p in (case.get("plaintiffs") or []) if s(p.get("name"))]
    defendants = [d for d in (case.get("defendants") or []) if s(d.get("name"))]
    if not plaintiffs:
        fail("sc100_case.plaintiffs needs at least one plaintiff with a name.")
    if not defendants:
        fail("sc100_case.defendants needs at least one defendant with a name.")

    names = [s(p["name"]) for p in plaintiffs]
    caption = ", ".join(names[:2]) + (", et al." if len(names) > 2 else "")
    for slot in ("caption_plaintiff_p2", "caption_plaintiff_p3", "caption_plaintiff_p4"):
        put(slot, caption)
    put("court_name_address", case.get("court_name_address"))

    def party(prefix, p):
        for key in ("name", "phone", "street", "city", "state", "zip"):
            put(f"{prefix}_{key}", p.get(key))
        mailing = [s(p.get(f"mailing_{k}")) for k in ("street", "city", "state", "zip")]
        home = [s(p.get(k)) for k in ("street", "city", "state", "zip")]
        if any(mailing) and [m.lower() for m in mailing] != [h.lower() for h in home]:
            for k in ("street", "city", "state", "zip"):
                put(f"{prefix}_mail_{k}", p.get(f"mailing_{k}"))
        elif any(mailing):
            notes.append(f"{prefix}: mailing address equals street address; left blank.")

    party("p1", plaintiffs[0])
    put("p1_email", plaintiffs[0].get("email"))
    if len(plaintiffs) > 1:
        party("p2", plaintiffs[1])
        put("p2_email", plaintiffs[1].get("email"))
    if len(plaintiffs) > 2:
        check("cb_more_than_two_plaintiffs")
        notes.append("More than two plaintiffs: attach form SC-100A listing the others.")
    if st.get("plaintiff_fictitious_name"):
        check("cb_fictitious_name")
        notes.append("Fictitious business name: attach form SC-103.")
    if st.get("plaintiff_payday_lender"):
        check("cb_payday_lender")

    d1 = defendants[0]
    party("d1", d1)
    agent = d1.get("agent") or {}
    if s(agent.get("name")):
        put("agent_name", agent.get("name"))
        put("agent_job", agent.get("job_title"))
        for k in ("street", "city", "state", "zip"):
            put(f"agent_{k}", agent.get(k))
    if len(defendants) > 1:
        check("cb_more_than_one_defendant")
        notes.append("More than one defendant: attach form SC-100A listing the others.")
    if st.get("defendant_military"):
        check("cb_defendant_military")
        notes.append("Defendant on active military duty: the form has no field for the name; write it by hand next to the box.")

    amount_text, amount = fmt_amount(case.get("claim_amount"))
    put("claim_amount", amount_text)
    put("why_owed", case.get("why_owed"))
    put("incident_date", fmt_date(case.get("incident_date"), pattern, "incident"))
    put("period_start", fmt_date(case.get("period_start"), pattern, "period start"))
    put("period_through", fmt_date(case.get("period_through"), pattern, "period through"))
    put("how_calculated", case.get("how_calculated"))
    if case.get("needs_more_space"):
        check("cb_more_space")
        notes.append('Item 3 continues on an attached sheet or MC-031 titled "SC-100, Item 3".')

    if st.get("asked_before_suing"):
        check("cb_asked_yes")
    else:
        check("cb_asked_no")
        put("asked_no_explain", case.get("asked_no_explanation"))

    venue = st.get("venue_basis")
    if venue not in VENUE_SLOT:
        fail(f"venue_basis {venue!r} is not one of {sorted(VENUE_SLOT)}.")
    check(VENUE_SLOT[venue])
    if venue == "other":
        put("venue_other_specify", case.get("venue_other_specify"))
    put("venue_zip", case.get("venue_zip"))
    if not s(case.get("venue_zip")):
        notes.append("Item 6 venue zip left blank (not known from the case).")

    if st.get("attorney_fee_dispute"):
        check("cb_fee_dispute_yes")
        if st.get("fee_arbitration_done"):
            check("cb_fee_arbitration")
            notes.append("Attorney fee arbitration done: attach form SC-101.")
    else:
        check("cb_fee_dispute_no")

    if st.get("suing_public_entity"):
        check("cb_public_entity_yes")
        claim_date = fmt_date(case.get("public_claim_filed_date"), pattern, "public-entity claim")
        if claim_date:
            check("cb_public_claim_filed")
            put("public_claim_date", claim_date)
        else:
            notes.append("Suing a public entity: a written claim must be filed with the entity first.")
    else:
        check("cb_public_entity_no")

    check("cb_over_12_yes" if st.get("over_12_claims") else "cb_over_12_no")

    if amount is None:
        notes.append("No claim amount: item 10 left unanswered.")
    else:
        check("cb_over_2500_yes" if amount > Decimal(2500) else "cb_over_2500_no")

    filing = fmt_date(case.get("filing_date"), pattern, "filing")
    put("sign_name_1", names[0])
    put("sign_date_1", filing)
    if len(names) > 1:
        put("sign_name_2", names[1])
        put("sign_date_2", filing)
    if not filing:
        notes.append("No filing date given: signature dates left blank.")

    never = fmap.get("never_fill", [])
    out = []
    for slot, value in values.items():
        fid = slot_field[slot]
        if any(n in fid for n in never):
            fail(f"Refusing to fill court-only field {fid}.")
        out.append({"field_id": fid, "page": fields[fid]["page"], "value": value, "slot": slot})
    out.sort(key=lambda v: (v["page"], v["field_id"]))
    emit({"sc100_field_values": out, "sc100_mapping_notes": notes})


if __name__ == "__main__":
    main()
