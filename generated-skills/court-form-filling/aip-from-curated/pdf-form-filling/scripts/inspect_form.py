"""inspect-form step: is the PDF fillable, what are its fields, what does each one mean?

stdin  {"currentState": {"pdf_path", "work_dir", ...}, "assets": {"form-profiles": ...}}
stdout {"is_fillable", "page_count", "encrypted", "has_xfa", "profile_name", "form_notes",
        "form_fields", "page_images", "inspect_warnings"}

CLI: python inspect_form.py <input.pdf> [work_dir]   (prints the same JSON)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pdf_forms as pf  # noqa: E402


def inspect(state, assets):
    pdf_path = pf.resolve_path(state["pdf_path"])
    if not os.path.exists(pdf_path):
        raise SystemExit(f"pdf_path not found: {pdf_path}")
    work_dir = pf.resolve_path(state.get("work_dir") or os.path.join(os.path.dirname(pdf_path), "form_work"))
    os.makedirs(work_dir, exist_ok=True)

    reader = pf.open_reader(pdf_path)
    encrypted = bool(reader.is_encrypted)
    acro = reader.trailer["/Root"].get("/AcroForm")
    has_xfa = bool(acro is not None and "/XFA" in acro.get_object())
    fields = pf.get_field_info(reader)
    unlocated = getattr(pf.get_field_info, "unlocated", [])
    fillable = any(f["type"] not in ("pushbutton",) for f in fields)

    profiles = pf.load_profiles(assets)
    profile_name, profile = pf.match_profile([f["field_id"] for f in fields], profiles)
    known = (profile or {}).get("fields", {})

    words = pf.word_boxes(pdf_path)
    heights = {i + 1: float(p.mediabox.height) for i, p in enumerate(reader.pages)}
    warnings = [f"Unable to determine location for field id: {fid}, ignoring" for fid in unlocated]
    out_fields = []
    for f in fields:
        item = {k: v for k, v in f.items() if k not in ("rect",)}
        meta = known.get(f["field_id"])
        if meta:
            item["label"] = meta["label"]
            item["who_fills"] = meta.get("who", "filer")
            if meta.get("conditional"):
                item["conditional"] = True
        else:
            rect = f.get("rect") or (f.get("radio_options") or [{}])[0].get("rect")
            item["label"] = pf.nearby_label(rect, heights.get(f["page"], 792), words.get(f["page"], []))
            if f["type"] == "pushbutton":
                item["who_fills"] = "never"
        if f["type"] == "pushbutton":
            item["who_fills"] = "never"
        if f.get("rect") and not meta:  # profile labels are exact; rects only help unknown forms
            item["rect"] = f["rect"]
        if "warning" in f:
            warnings.append(f"{f['field_id']}: {f['warning']}")
        out_fields.append(item)

    images = pf.render_pages(pdf_path, os.path.join(work_dir, "pages"))
    if not images:
        warnings.append("pdftoppm unavailable: no page images rendered; rely on labels/pdftotext.")

    return {
        "work_dir": work_dir,
        "pdf_path": pdf_path,
        "is_fillable": fillable,
        "page_count": len(reader.pages),
        "encrypted": encrypted,
        "has_xfa": has_xfa,
        "profile_name": profile_name,
        "form_notes": (profile or {}).get("notes", []),
        "form_fields": out_fields if fillable else [],
        "page_images": images,
        "inspect_warnings": warnings,
    }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        import json

        st = {"pdf_path": sys.argv[1]}
        if len(sys.argv) > 2:
            st["work_dir"] = sys.argv[2]
        print(json.dumps(inspect(st, {}), indent=2))
    else:
        state, assets = pf.read_step_input()
        pf.emit(inspect(state, assets))
