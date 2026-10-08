"""fill-fields step: validate the field-value plan against the PDF (and the form's
profile rules, e.g. SC-100), then write the filled PDF.

stdin  {"currentState": {"pdf_path", "output_pdf", "field_values": [{"field_id", "value", "page"?}], ...},
        "assets": {"form-profiles": ...}}
stdout {"fill_ok", "fill_errors", "fill_warnings", "auto_changes", "applied_values", "output_pdf"}
        On errors nothing is written; fix field_values and re-run.

CLI: python fill_fields.py <input.pdf> <field_values.json> <output.pdf>
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pdf_forms as pf  # noqa: E402

TRUE_WORDS = {"true", "yes", "y", "x", "checked", "on", "check"}
FALSE_WORDS = {"false", "no", "n", "unchecked", "off", "", "none"}


def parse_amount(text):
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(text or ""))
    return float(m.group(0).replace(",", "")) if m else None


def normalize(entry, info, errors, changes):
    """Return the value to write, or None to leave the field untouched."""
    fid, value = entry["field_id"], entry.get("value")
    t = info["type"]
    if t == "pushbutton":
        errors.append(f"ERROR: `{fid}` is a button (Print/Save/Reset), not a data field. Remove it.")
        return None
    if t == "checkbox":
        on, off = info.get("checked_value"), info.get("unchecked_value", "/Off")
        if isinstance(value, bool):
            return on if value else off
        sval = str(value).strip() if value is not None else ""
        if sval in (on, off):
            return sval
        if sval.lstrip("/") == str(on).lstrip("/"):
            return on
        if sval.lower() in TRUE_WORDS:
            changes.append(f"{fid}: '{sval}' -> checked value {on}")
            return on
        if sval.lower() in FALSE_WORDS:
            return off
        errors.append(
            f'ERROR: Invalid value "{value}" for checkbox field "{fid}". The checked value is "{on}" and the unchecked value is "{off}"'
        )
        return None
    if value is None:
        return None
    if t == "radio_group":
        opts = [o["value"] for o in info["radio_options"]]
        if value not in opts:
            errors.append(f'ERROR: Invalid value "{value}" for radio group field "{fid}". Valid values are: {opts}')
            return None
    elif t == "choice":
        opts = [o["value"] for o in info["choice_options"]]
        if value not in opts:
            errors.append(f'ERROR: Invalid value "{value}" for choice field "{fid}". Valid values are: {opts}')
            return None
    return str(value)


def is_set(values, infos, fid):
    v = values.get(fid)
    if v is None or v == "":
        return False
    info = infos.get(fid, {})
    if info.get("type") == "checkbox":
        return v == info.get("checked_value")
    return True


def apply_rules(profile, values, infos, errors, warnings, changes):
    meta = profile.get("fields", {})
    for fid, v in list(values.items()):
        who = meta.get(fid, {}).get("who")
        if who in ("clerk", "court", "never") and is_set(values, infos, fid):
            errors.append(f"ERROR: `{fid}` is filled by the {who if who != 'never' else 'nobody'} — {meta[fid]['label']} Remove it.")
    # Deterministic fixes (copy headers, strip "$", derive threshold boxes) run before the checks.
    first = ("same_value", "currency", "amount_threshold")
    rules = sorted(profile.get("rules", []), key=lambda r: r["type"] not in first)
    for rule in rules:
        t, name = rule["type"], rule.get("name", rule["type"])
        if t == "exclusive":
            on = [f for f in rule["fields"] if is_set(values, infos, f)]
            if len(on) > 1:
                errors.append(f"ERROR: {name}: check only one of {on}")
            elif not on and rule.get("require_one"):
                warnings.append(f"WARNING: {name}: nothing checked — answer it from the facts.")
        elif t == "same_value":
            given = {values[f] for f in rule["fields"] if is_set(values, infos, f)}
            if len(given) > 1:
                errors.append(f"ERROR: {name}: values differ {sorted(given)}; use identical text.")
            elif len(given) == 1:
                val = given.pop()
                for f in rule["fields"]:
                    if not is_set(values, infos, f):
                        values[f] = val
                        changes.append(f"{f}: copied '{val}' ({name})")
        elif t == "currency":
            f = rule["field"]
            if is_set(values, infos, f):
                raw = values[f]
                amt = parse_amount(raw)
                if amt is None:
                    errors.append(f"ERROR: {name}: '{raw}' is not an amount.")
                else:
                    # Only drop the currency sign; keep the figure exactly as the facts state it.
                    clean = raw.replace("$", "").replace("USD", "").strip()
                    if clean != raw:
                        values[f] = clean
                        changes.append(f"{f}: '{raw}' -> '{clean}' (currency sign removed; '$' is pre-printed)")
        elif t == "amount_threshold":
            if not is_set(values, infos, rule["amount_field"]):
                continue
            amt = parse_amount(values[rule["amount_field"]])
            if amt is None:
                continue
            want, other = (rule["above"], rule["at_or_below"]) if amt > rule["threshold"] else (rule["at_or_below"], rule["above"])
            if is_set(values, infos, other):
                errors.append(f"ERROR: {name}: amount {amt:,.2f} vs threshold {rule['threshold']:,} means `{want}` must be checked, not `{other}`.")
            elif not is_set(values, infos, want):
                values[want] = infos[want]["checked_value"]
                changes.append(f"{want}: checked ({name}, amount {amt:,.2f})")
        elif t == "amount_limit":
            if is_set(values, infos, rule["amount_field"]):
                amt = parse_amount(values[rule["amount_field"]]) or 0
                if amt > rule["limit"]:
                    warnings.append(f"WARNING: {name}: {amt:,.2f} exceeds the ${rule['limit']:,} limit for individuals.")
                elif amt > rule.get("business_limit", amt):
                    warnings.append(
                        f"WARNING: {name}: {amt:,.2f} exceeds ${rule['business_limit']:,}, the limit for corporations, partnerships, public entities and other businesses — fine only if the plaintiff is an individual/sole proprietor."
                    )
        elif t == "requires":
            if is_set(values, infos, rule["if_set"]):
                missing = [f for f in rule["then"] if not is_set(values, infos, f)]
                if missing:
                    warnings.append(f"WARNING: {name}: also fill {missing}")
        elif t == "forbids":
            if is_set(values, infos, rule["if_set"]):
                extra = [f for f in rule["then"] if is_set(values, infos, f)]
                if extra:
                    errors.append(f"ERROR: {name}: leave {extra} blank")
        elif t == "requires_always":
            missing = [f for f in rule["fields"] if not is_set(values, infos, f)]
            if missing:
                warnings.append(f"WARNING: {name}: empty {missing} — fill them if the facts give the information.")
        elif t == "requires_one_of":
            if not any(is_set(values, infos, f) for f in rule["fields"]):
                warnings.append(f"WARNING: {name}: fill one of {rule['fields']}")


def fill(state, assets):
    pdf_path = pf.resolve_path(state["pdf_path"])
    output_pdf = pf.resolve_path(state["output_pdf"])
    entries = state.get("field_values") or []
    if isinstance(entries, dict):  # tolerate {field_id: value}
        entries = [{"field_id": k, "value": v} for k, v in entries.items()]

    reader = pf.open_reader(pdf_path)
    infos = {f["field_id"]: f for f in pf.get_field_info(reader)}
    errors, warnings, changes = [], [], []
    values = {}
    for e in entries:
        fid = e.get("field_id")
        info = infos.get(fid)
        if not info:
            close = [k for k in infos if fid and fid.split(".")[-1] in k][:5]
            errors.append(f"ERROR: `{fid}` is not a valid field ID" + (f" (did you mean {close}?)" if close else ""))
            continue
        if "page" in e and e["page"] is not None and int(e["page"]) != info["page"]:
            errors.append(f"ERROR: Incorrect page number for `{fid}` (got {e['page']}, expected {info['page']})")
            continue
        v = normalize(e, info, errors, changes)
        if v is not None:
            values[fid] = v

    profiles = pf.load_profiles(assets)
    _, profile = pf.match_profile(list(infos), profiles)
    if profile:
        apply_rules(profile, values, infos, errors, warnings, changes)

    result = {"fill_errors": errors, "fill_warnings": warnings, "auto_changes": changes, "output_pdf": output_pdf}
    if errors:
        result.update(fill_ok=False, applied_values=[])
        return result

    by_page = {}
    for fid, v in values.items():
        by_page.setdefault(infos[fid]["page"], {})[fid] = v
    removed = pf.write_filled(pdf_path, by_page, output_pdf)
    if removed:
        changes.append(f"removed {' and '.join(removed)} from the output so viewers show the AcroForm values")
    result.update(
        fill_ok=True,
        applied_values=[{"field_id": k, "page": infos[k]["page"], "value": v} for k, v in values.items()],
    )
    return result


if __name__ == "__main__":
    if len(sys.argv) == 4:
        with open(sys.argv[2]) as f:
            fv = json.load(f)
        res = fill({"pdf_path": sys.argv[1], "field_values": fv, "output_pdf": sys.argv[3]}, {})
        for line in res["fill_errors"] + res["fill_warnings"] + res["auto_changes"]:
            print(line)
        print("OK: wrote " + res["output_pdf"] if res["fill_ok"] else "Not written; fix the errors above.")
        sys.exit(0 if res["fill_ok"] else 1)
    state, assets = pf.read_step_input()
    pf.emit(fill(state, assets))
