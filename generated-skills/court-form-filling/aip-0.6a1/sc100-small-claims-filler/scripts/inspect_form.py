"""Step `inspect-form`: open the blank form, list its fillable fields, and pick the route.

stdin:  {"state": {"form_pdf_path"}, "assets": {"sc100_field_map": <json text>}}
stdout: {"form_route": "sc100" | "fillable" | "non_fillable", "form_fields": [...], "form_summary": "..."}

Route rules:
- no AcroForm fields                                   -> non_fillable (annotate visually)
- every SC-100 field-map slot resolves to exactly one
  field of this form                                   -> sc100 (deterministic mapping)
- otherwise (other form, or an SC-100 revision whose
  field ids no longer match the map)                   -> fillable (map by tooltip/label)
"""
import json

from pdf_form_lib import emit, get_field_info, open_reader, read_stdin


def load_map(assets):
    raw = assets.get("sc100_field_map")
    if raw is None:
        with open("../assets/sc100_field_map.json") as f:
            return json.load(f)
    return json.loads(raw) if isinstance(raw, str) else raw


def resolve(field_ids, suffix):
    return [fid for fid in field_ids if fid == suffix or fid.endswith("." + suffix)]


def main():
    payload = read_stdin()
    state = payload.get("state", {})
    path = state["form_pdf_path"]
    reader = open_reader(path)
    fields = get_field_info(reader)
    pages = len(reader.pages)

    if not fields:
        emit({
            "form_route": "non_fillable",
            "form_fields": [],
            "form_summary": f"{pages} pages, no fillable form fields: annotate visually.",
        })
        return

    fmap = load_map(payload.get("assets", {}))
    ids = [f["field_id"] for f in fields]
    unresolved = [k for k, sfx in fmap["fields"].items() if len(resolve(ids, sfx)) != 1]
    is_sc100 = any(fid.startswith("SC-100[") for fid in ids)
    route = "sc100" if is_sc100 and not unresolved else "fillable"
    summary = f"{pages} pages, {len(fields)} fillable fields."
    if is_sc100 and unresolved:
        summary += f" SC-100 detected but {len(unresolved)} field-map slots did not resolve ({', '.join(unresolved[:8])}); map by tooltip instead."
    elif route == "sc100":
        summary += " SC-100 field map resolves completely."
    emit({"form_route": route, "form_fields": fields, "form_summary": summary})


if __name__ == "__main__":
    main()
