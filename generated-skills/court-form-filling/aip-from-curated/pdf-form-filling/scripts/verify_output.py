"""verify-output step: read the written PDF back and lay out what is actually in it.

Fillable forms: every non-empty field with its label, intended-vs-readback mismatches,
and the filer-fillable fields still empty. Non-fillable forms: the FreeText annotations
per page. Both: rendered PNGs of the output pages for visual inspection.

stdin  {"currentState": {"output_pdf", "is_fillable", "work_dir", "applied_values"?, "form_fields"?}}
stdout {"verify_report", "readback_mismatches", "output_images"}
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pdf_forms as pf  # noqa: E402


def verify(state, assets):
    out_pdf = pf.resolve_path(state["output_pdf"])
    if not os.path.exists(out_pdf):
        raise SystemExit(f"output_pdf not found: {out_pdf}")
    work_dir = pf.resolve_path(state.get("work_dir") or os.path.dirname(out_pdf))
    lines, mismatches = [], []

    if state.get("is_fillable", True):
        got = pf.read_values(out_pdf)
        labels = {f["field_id"]: f.get("label", "") for f in state.get("form_fields") or []}
        who = {f["field_id"]: f.get("who_fills", "filer") for f in state.get("form_fields") or []}
        for a in state.get("applied_values") or []:
            if got.get(a["field_id"], "") != str(a["value"]) and not (
                str(a["value"]) == "/Off" and got.get(a["field_id"]) in (None, "/Off", "")
            ):
                mismatches.append(f"{a['field_id']}: intended {a['value']!r}, file has {got.get(a['field_id'])!r}")
        filled = {k: v for k, v in got.items() if v not in ("", "/Off")}
        lines.append(f"FILLED ({len(filled)} fields):")
        for fid, v in filled.items():
            lines.append(f"- {fid} = {v!r}" + (f"  [{labels[fid][:90]}]" if labels.get(fid) else ""))
        cond = {f["field_id"] for f in state.get("form_fields") or [] if f.get("conditional")}
        _, profile = pf.match_profile(list(labels), pf.load_profiles(assets))
        answered = set()  # empty halves of Yes/No pairs (or a-e groups) whose question is answered
        for rule in (profile or {}).get("rules", []):
            if rule["type"] == "exclusive" and any(f in filled for f in rule["fields"]):
                answered |= set(rule["fields"])
        empty = [fid for fid in labels if fid not in filled and who.get(fid) in ("filer", "optional") and fid not in answered]
        core = [fid for fid in empty if fid not in cond]
        lines.append(f"EMPTY core filer fields ({len(core)}) — each must be genuinely unknown from the facts:")
        for fid in core:
            lines.append(f"- {fid}  [{labels[fid][:110]}]")
        situational = [fid for fid in empty if fid in cond]
        if situational:
            lines.append(f"EMPTY situational fields ({len(situational)}) — fill only if their condition applies:")
            lines.append("  " + "; ".join(labels[fid][:70] for fid in situational))
        lines.append("Note: rendered images depend on system fonts (field text uses Arial, checkbox marks ZapfDingbats) and may show values blank; trust the FILLED list for values.")
    else:
        reader = pf.open_reader(out_pdf)
        n = 0
        for i, page in enumerate(reader.pages, start=1):
            for ann in page.get("/Annots", []) or []:
                ann = ann.get_object()
                if ann.get("/Subtype") == "/FreeText":
                    n += 1
                    lines.append(f"- page {i} {[round(float(x)) for x in ann['/Rect']]}: {ann.get('/Contents')!r}")
        lines.insert(0, f"ANNOTATIONS ({n}):")

    images = pf.render_pages(out_pdf, os.path.join(work_dir, "verify"), prefix="filled")
    return {
        "verify_report": "\n".join(lines),
        "readback_mismatches": mismatches,
        "output_images": [im["path"] for im in images],
    }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(verify({"output_pdf": sys.argv[1]}, {})["verify_report"])
    else:
        state, assets = pf.read_step_input()
        pf.emit(verify(state, assets))
