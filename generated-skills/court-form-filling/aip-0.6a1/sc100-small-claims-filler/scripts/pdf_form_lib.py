"""Shared helpers for the form-filling steps (adapted from the pdf skill's
extract_form_field_info.py and fill_fillable_fields.py).

Differences from the originals:
- Encrypted forms (the official SC-100 is AES-encrypted with an empty user
  password) are decrypted up front; pypdf needs the `cryptography` package for AES.
- Each field carries its tooltip (/TU), which on court forms is the printed label.
- Values are written, then read back to verify; the output is never encrypted and
  the XFA packet is dropped so viewers render the AcroForm values.
"""
import json
import sys

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject


def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.write("\n")


def fail(msg):
    sys.stderr.write(msg.rstrip() + "\n")
    sys.exit(1)


def read_stdin():
    raw = sys.stdin.read()
    try:
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        fail(f"stdin is not JSON: {e}")


def open_reader(path):
    try:
        reader = PdfReader(path)
    except FileNotFoundError:
        fail(f"PDF not found: {path}")
    if reader.is_encrypted:
        try:
            ok = reader.decrypt("")
        except Exception as e:  # DependencyError when cryptography is missing
            fail(f"Cannot decrypt {path}: {e}. AES-encrypted forms need the `cryptography` package.")
        if not ok:
            fail(f"{path} needs a user password; cannot open it.")
    return reader


# This matches the format used by PdfReader `get_fields` and `update_page_form_field_values` methods.
def get_full_annotation_field_id(annotation):
    components = []
    while annotation:
        field_name = annotation.get("/T")
        if field_name:
            components.append(field_name)
        annotation = annotation.get("/Parent")
    return ".".join(reversed(components)) if components else None


def _clean(text):
    return " ".join(str(text).split()) if text else ""


def make_field_dict(field, field_id):
    field_dict = {"field_id": field_id}
    ft = field.get("/FT")
    if ft == "/Tx":
        field_dict["type"] = "text"
    elif ft == "/Btn":
        field_dict["type"] = "checkbox"  # radio groups handled separately
        states = field.get("/_States_", [])
        if len(states) == 2:
            # "/Off" is the unchecked value; it can be first or second in "/_States_".
            if "/Off" in states:
                field_dict["checked_value"] = states[0] if states[0] != "/Off" else states[1]
                field_dict["unchecked_value"] = "/Off"
            else:
                field_dict["checked_value"] = states[0]
                field_dict["unchecked_value"] = states[1]
                field_dict["warning"] = "Unexpected checkbox states; visually verify the result if you check it."
    elif ft == "/Ch":
        field_dict["type"] = "choice"
        states = field.get("/_States_", [])
        field_dict["choice_options"] = [{"value": s[0], "text": s[1]} for s in states]
    else:
        field_dict["type"] = f"unknown ({ft})"
    tooltip = _clean(field.get("/TU"))
    if tooltip:
        field_dict["tooltip"] = tooltip
    return field_dict


def get_field_info(reader):
    """List of fillable fields: field_id, page (1-based), type, rect, tooltip, and
    checked_value / radio_options / choice_options per type. Sorted by page, then
    top-to-bottom, then left-to-right."""
    fields = reader.get_fields() or {}
    field_info_by_id = {}
    possible_radio_names = set()
    for field_id, field in fields.items():
        # Skip container fields, except possible radio-button parents.
        if field.get("/Kids"):
            if field.get("/FT") == "/Btn":
                possible_radio_names.add(field_id)
            continue
        field_info_by_id[field_id] = make_field_dict(field, field_id)

    radio_fields_by_id = {}
    for page_index, page in enumerate(reader.pages):
        for ann in page.get("/Annots", []) or []:
            ann = ann.get_object()
            field_id = get_full_annotation_field_id(ann)
            if field_id in field_info_by_id:
                field_info_by_id[field_id]["page"] = page_index + 1
                field_info_by_id[field_id]["rect"] = [round(float(x), 1) for x in ann.get("/Rect", [0, 0, 0, 0])]
            elif field_id in possible_radio_names:
                try:
                    on_values = [v for v in ann["/AP"]["/N"] if v != "/Off"]
                except KeyError:
                    continue
                if len(on_values) == 1:
                    rect = [round(float(x), 1) for x in ann.get("/Rect", [0, 0, 0, 0])]
                    entry = radio_fields_by_id.setdefault(
                        field_id,
                        {"field_id": field_id, "type": "radio_group", "page": page_index + 1, "radio_options": []},
                    )
                    entry["radio_options"].append({"value": on_values[0], "rect": rect})

    # Fields without an annotation have no known location; they cannot be filled reliably.
    located = [f for f in field_info_by_id.values() if "page" in f]

    def sort_key(f):
        rect = (f["radio_options"][0]["rect"] if "radio_options" in f else f.get("rect")) or [0, 0, 0, 0]
        return [f.get("page"), -rect[1], rect[0]]

    out = located + list(radio_fields_by_id.values())
    out.sort(key=sort_key)
    return out


def validation_error_for_field_value(field_info, field_value):
    field_type = field_info["type"]
    field_id = field_info["field_id"]
    if field_type == "checkbox":
        checked_val = field_info.get("checked_value")
        unchecked_val = field_info.get("unchecked_value")
        if field_value not in (checked_val, unchecked_val):
            return f'Invalid value "{field_value}" for checkbox "{field_id}". Checked value is "{checked_val}", unchecked is "{unchecked_val}".'
    elif field_type == "radio_group":
        option_values = [opt["value"] for opt in field_info["radio_options"]]
        if field_value not in option_values:
            return f'Invalid value "{field_value}" for radio group "{field_id}". Valid values: {option_values}'
    elif field_type == "choice":
        choice_values = [opt["value"] for opt in field_info["choice_options"]]
        if field_value not in choice_values:
            return f'Invalid value "{field_value}" for choice field "{field_id}". Valid values: {choice_values}'
    elif not isinstance(field_value, str):
        return f'Text field "{field_id}" needs a string value, got {type(field_value).__name__}.'
    return None


# pypdf has a bug setting selection-list values: get_inherited(/Opt) returns
# [[value, text], ...] and a later "\n".join fails. Return only the values.
def monkeypatch_pypdf_method():
    from pypdf.constants import FieldDictionaryAttributes
    from pypdf.generic import DictionaryObject

    original_get_inherited = DictionaryObject.get_inherited

    def patched_get_inherited(self, key, default=None):
        result = original_get_inherited(self, key, default)
        if key == FieldDictionaryAttributes.Opt:
            if isinstance(result, list) and all(isinstance(v, list) and len(v) == 2 for v in result):
                result = [r[0] for r in result]
        return result

    DictionaryObject.get_inherited = patched_get_inherited


def _norm(v):
    if v is None:
        return ""
    return str(v)


def fill_and_verify(input_pdf, field_values, output_pdf):
    """field_values: list of {"field_id", "value", optional "page"}. Validates every
    id/value against the form, writes output_pdf, reads it back and checks that each
    value persisted and that no other field holds a value."""
    if not isinstance(field_values, list) or not field_values:
        fail("field_values must be a non-empty list of {field_id, value} objects.")
    monkeypatch_pypdf_method()
    reader = open_reader(input_pdf)
    info = {f["field_id"]: f for f in get_field_info(reader)}

    errors = []
    by_page = {}
    seen = set()
    for fv in field_values:
        fid = fv.get("field_id")
        if fid not in info:
            errors.append(f"`{fid}` is not a valid field ID")
            continue
        if fid in seen:
            errors.append(f"`{fid}` is set more than once")
            continue
        seen.add(fid)
        if "page" in fv and fv["page"] != info[fid]["page"]:
            errors.append(f"Incorrect page for `{fid}` (got {fv['page']}, expected {info[fid]['page']})")
            continue
        if "value" not in fv:
            errors.append(f"`{fid}` has no value")
            continue
        err = validation_error_for_field_value(info[fid], fv["value"])
        if err:
            errors.append(err)
            continue
        by_page.setdefault(info[fid]["page"], {})[fid] = fv["value"]
    if errors:
        fail("Field values rejected:\n" + "\n".join(errors))

    writer = PdfWriter(clone_from=reader)
    for page, values in by_page.items():
        writer.update_page_form_field_values(writer.pages[page - 1], values, auto_regenerate=False)
    # Viewers prefer an XFA packet over AcroForm values; drop it so the filled values show.
    acro = writer._root_object.get("/AcroForm")
    acro = acro.get_object() if acro is not None else None
    if acro is not None and "/XFA" in acro:
        del acro[NameObject("/XFA")]
    # Needed by many viewers to format form values; may trigger a "save changes" prompt.
    writer.set_need_appearances_writer(True)
    with open(output_pdf, "wb") as f:
        writer.write(f)

    # Read back.
    check = PdfReader(output_pdf)
    expected = {fid: v for values in by_page.values() for fid, v in values.items()}
    mismatches, unexpected = [], []
    for fid, field in (check.get_fields() or {}).items():
        if field.get("/Kids") and fid not in expected:
            continue
        got = _norm(field.get("/V"))
        if fid in expected:
            if got != _norm(expected[fid]):
                mismatches.append({"field_id": fid, "expected": expected[fid], "got": got})
        elif got not in ("", "/Off"):
            unexpected.append({"field_id": fid, "value": got})
    report = {
        "output_pdf": output_pdf,
        "fields_set": len(expected),
        "encrypted": bool(check.is_encrypted),
        "mismatches": mismatches,
        "unexpected_nonempty": unexpected,
        "verified": not mismatches and not unexpected and not check.is_encrypted,
    }
    if not report["verified"]:
        fail("Filled PDF failed read-back verification: " + json.dumps(report))
    return report
