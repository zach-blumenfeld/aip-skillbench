#!/usr/bin/env python3
"""PDF form toolkit: inspect, extract, render, fill, verify (fillable forms) and
annotate (non-fillable forms).

Requires: Python >= 3.10, pypdf >= 5.1 (+ cryptography for encrypted PDFs),
Pillow (render, validation images), and one of pymupdf, pdf2image, or the poppler
`pdftoppm` binary (render; tried in that order).

Usage (run from the skill root):
  python3 scripts/pdf_forms.py check <pdf>
  python3 scripts/pdf_forms.py extract <pdf> <field_info.json>
  python3 scripts/pdf_forms.py render <pdf> <out_dir> [--max-dim 1000]
  python3 scripts/pdf_forms.py fill <pdf> <field_values.json> <out.pdf> [--keep-xfa]
  python3 scripts/pdf_forms.py dump <pdf> [--all]
  python3 scripts/pdf_forms.py check-boxes <fields.json>
  python3 scripts/pdf_forms.py validation-image <page> <fields.json> <in.png> <out.png>
  python3 scripts/pdf_forms.py annotate <pdf> <fields.json> <out.pdf>
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    sys.exit("ERROR: pypdf is not installed (pip install pypdf). It is required by every subcommand.")


def open_reader(path):
    reader = PdfReader(path)
    if reader.is_encrypted:
        # Court forms are commonly encrypted with an empty user password (permissions only).
        try:
            reader.decrypt("")
        except Exception as e:  # noqa: BLE001
            sys.exit(f"ERROR: {path} is encrypted and could not be opened with an empty password: {e}")
    return reader


# ---------------------------------------------------------------- field info
# Matches the naming used by PdfReader.get_fields and update_page_form_field_values.
def get_full_annotation_field_id(annotation):
    components = []
    while annotation:
        field_name = annotation.get("/T")
        if field_name:
            components.append(field_name)
        annotation = annotation.get("/Parent")
    return ".".join(reversed(components)) if components else None


def make_field_dict(field, field_id):
    field_dict = {"field_id": field_id}
    ft = field.get("/FT")
    if ft == "/Tx":
        field_dict["type"] = "text"
    elif ft == "/Btn":
        field_dict["type"] = "checkbox"  # radio groups handled separately
        states = field.get("/_States_", [])
        if len(states) == 2:
            # "/Off" is the unchecked value (PDF 32000-1:2008, 12.7.4.2.3); it may be first or second.
            if "/Off" in states:
                field_dict["checked_value"] = states[0] if states[0] != "/Off" else states[1]
                field_dict["unchecked_value"] = "/Off"
            else:
                print(f"WARNING: unexpected state values for checkbox `{field_id}`; its checked/unchecked "
                      "values may be wrong. If you check it, visually verify the result.")
                field_dict["checked_value"] = states[0]
                field_dict["unchecked_value"] = states[1]
    elif ft == "/Ch":
        field_dict["type"] = "choice"
        states = field.get("/_States_", [])
        # Options are [export_value, display_text] pairs or plain strings.
        field_dict["choice_options"] = [
            {"value": str(s), "text": str(s)} if isinstance(s, str) else {"value": s[0], "text": s[1]}
            for s in states]
    else:
        field_dict["type"] = f"unknown ({ft})"
    tooltip = field.get("/TU")
    if tooltip:
        field_dict["tooltip"] = " ".join(str(tooltip).split())
    flags = int(field.get("/Ff", 0) or 0)
    if flags & 1:
        field_dict["read_only"] = True
    if ft == "/Btn" and flags & 65536:
        field_dict["type"] = "pushbutton"  # Print/Save/Reset buttons: never fill
    return field_dict


def get_field_info(reader):
    """List of fillable fields sorted by page, then top-to-bottom, then left-to-right."""
    fields = reader.get_fields() or {}
    field_info_by_id = {}
    possible_radio_names = set()
    for field_id, field in fields.items():
        # Skip containers with children, except possible radio-button parents.
        if field.get("/Kids"):
            if field.get("/FT") == "/Btn":
                possible_radio_names.add(field_id)
            continue
        field_info_by_id[field_id] = make_field_dict(field, field_id)

    # Bounding rects live in the page annotations. Radio options have one annotation
    # per choice, all sharing the parent field name.
    radio_fields_by_id = {}
    for page_index, page in enumerate(reader.pages):
        for ann in page.get("/Annots", []) or []:
            ann = ann.get_object()
            field_id = get_full_annotation_field_id(ann)
            if field_id in field_info_by_id:
                field_info_by_id[field_id]["page"] = page_index + 1
                field_info_by_id[field_id]["rect"] = [float(x) for x in ann.get("/Rect")]
            elif field_id in possible_radio_names:
                try:
                    on_values = [v for v in ann["/AP"]["/N"] if v != "/Off"]
                except KeyError:
                    continue
                if len(on_values) == 1:
                    rect = [float(x) for x in ann.get("/Rect")]
                    radio = radio_fields_by_id.setdefault(field_id, {
                        "field_id": field_id, "type": "radio_group",
                        "page": page_index + 1, "radio_options": []})
                    # macOS Preview may not display selected radio buttons; Chrome/Firefox/Acrobat do.
                    radio["radio_options"].append({"value": on_values[0], "rect": rect})

    # Some PDFs define fields without annotations, so their location is unknown; ignore them.
    located = []
    for info in field_info_by_id.values():
        if "page" in info:
            located.append(info)
        else:
            print(f"Unable to determine location for field id: {info.get('field_id')}, ignoring")

    def sort_key(f):
        rect = (f["radio_options"][0]["rect"] if "radio_options" in f else f.get("rect")) or [0, 0, 0, 0]
        return [f.get("page"), [-rect[1], rect[0]]]

    out = located + list(radio_fields_by_id.values())
    out.sort(key=sort_key)
    return out


# ------------------------------------------------------------------- check
def cmd_check(a):
    reader = open_reader(a.pdf)
    fields = reader.get_fields() or {}
    acro = reader.trailer["/Root"].get("/AcroForm")
    acro = acro.get_object() if acro else {}
    names = list(fields)
    form_id = None
    if any(n.startswith("SC-100[0]") for n in names):
        form_id = "SC-100"
    summary = {
        "fillable": bool(fields),
        "field_count": sum(1 for f in fields.values() if not f.get("/Kids")),
        "pages": len(reader.pages),
        "encrypted": PdfReader(a.pdf).is_encrypted,
        "has_xfa": "/XFA" in acro,
        "form_id": form_id,
    }
    print(json.dumps(summary, indent=2))
    if fields:
        print("This PDF has fillable form fields")
    else:
        print("This PDF does not have fillable form fields; you will need to visually determine where to enter data")


def cmd_extract(a):
    info = get_field_info(open_reader(a.pdf))
    with open(a.out, "w") as f:
        json.dump(info, f, indent=2)
    print(f"Wrote {len(info)} fields to {a.out}")


# ------------------------------------------------------------------ render
def _render_pages(pdf):
    try:
        # PyMuPDF draws filled form widgets (checkmarks included) most faithfully.
        import pymupdf
        from PIL import Image
        doc = pymupdf.open(pdf)
        if doc.needs_pass:
            doc.authenticate("")
        out = []
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            out.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
        return out
    except ImportError:
        pass
    try:
        from pdf2image import convert_from_path
        return convert_from_path(pdf, dpi=200)
    except ImportError:
        pass
    if not shutil.which("pdftoppm"):
        sys.exit("ERROR: need pymupdf or pdf2image (pip) or pdftoppm (poppler-utils) to render pages")
    from PIL import Image
    tmp = tempfile.mkdtemp()
    subprocess.run(["pdftoppm", "-png", "-r", "200", pdf, os.path.join(tmp, "p")], check=True)
    return [Image.open(os.path.join(tmp, n)) for n in sorted(os.listdir(tmp))]


def cmd_render(a):
    os.makedirs(a.out_dir, exist_ok=True)
    images = _render_pages(a.pdf)
    for i, image in enumerate(images):
        w, h = image.size
        if w > a.max_dim or h > a.max_dim:  # keep both sides under max_dim
            s = min(a.max_dim / w, a.max_dim / h)
            image = image.resize((int(w * s), int(h * s)))
        path = os.path.join(a.out_dir, f"page_{i + 1}.png")
        image.save(path)
        print(f"Saved page {i + 1} as {path} (size: {image.size})")
    print(f"Converted {len(images)} pages to PNG images")


# -------------------------------------------------------------------- fill
def validation_error_for_field_value(info, value):
    t, fid = info["type"], info["field_id"]
    if t == "pushbutton":
        return f'ERROR: "{fid}" is a push button (Print/Save/Reset); never set it'
    if t == "checkbox":
        c, u = info.get("checked_value"), info.get("unchecked_value")
        if value not in (c, u):
            return f'ERROR: Invalid value "{value}" for checkbox field "{fid}". The checked value is "{c}" and the unchecked value is "{u}"'
    elif t == "radio_group":
        opts = [o["value"] for o in info["radio_options"]]
        if value not in opts:
            return f'ERROR: Invalid value "{value}" for radio group field "{fid}". Valid values are: {opts}'
    elif t == "choice":
        opts = [o["value"] for o in info["choice_options"]]
        if value not in opts:
            return f'ERROR: Invalid value "{value}" for choice field "{fid}". Valid values are: {opts}'
    elif t == "text" and not isinstance(value, str):
        return f'ERROR: Text field "{fid}" needs a string value, got {type(value).__name__}'
    return None


def monkeypatch_pypdf_choice_bug():
    # pypdf (<= 5.7) joins /Opt for list-box fields, but /Opt can be [[value, text], ...],
    # which raises TypeError. Return only the value strings for that case.
    from pypdf.constants import FieldDictionaryAttributes
    from pypdf.generic import DictionaryObject
    original = DictionaryObject.get_inherited

    def patched(self, key, default=None):
        result = original(self, key, default)
        if key == FieldDictionaryAttributes.Opt and isinstance(result, list) and \
                all(isinstance(v, list) and len(v) == 2 for v in result):
            result = [r[0] for r in result]
        return result

    DictionaryObject.get_inherited = patched


def cmd_fill(a):
    monkeypatch_pypdf_choice_bug()
    with open(a.values) as f:
        fields = json.load(f)
    reader = open_reader(a.pdf)
    by_id = {f["field_id"]: f for f in get_field_info(reader)}
    has_error = False
    by_page = {}
    for field in fields:
        existing = by_id.get(field["field_id"])
        if not existing:
            has_error = True
            print(f"ERROR: `{field['field_id']}` is not a valid field ID")
            continue
        if field.get("page") != existing["page"]:
            has_error = True
            print(f"ERROR: Incorrect page number for `{field['field_id']}` (got {field.get('page')}, expected {existing['page']})")
            continue
        if "value" in field:
            err = validation_error_for_field_value(existing, field["value"])
            if err:
                has_error = True
                print(err)
                continue
            if existing.get("read_only"):
                print(f"NOTE: `{field['field_id']}` is read-only in the form (usually a mirror of another field); setting it anyway")
            by_page.setdefault(field["page"], {})[field["field_id"]] = field["value"]
    if has_error:
        print("No output written; fix the errors above and rerun.")
        sys.exit(1)

    writer = PdfWriter(clone_from=reader)
    for page, values in by_page.items():
        writer.update_page_form_field_values(writer.pages[page - 1], values, auto_regenerate=False)
    # Needed for many viewers to render the values; may trigger a "save changes" prompt.
    writer.set_need_appearances_writer(True)
    acro = writer._root_object.get("/AcroForm")
    if acro is not None and "/XFA" in acro.get_object() and not a.keep_xfa:
        # XFA-capable viewers (Acrobat) render the empty XFA data instead of the AcroForm values.
        del acro.get_object()["/XFA"]
        print("Removed the XFA layer so viewers show the filled AcroForm values")
    with open(a.out, "wb") as f:
        writer.write(f)
    print(f"Filled {sum(len(v) for v in by_page.values())} fields; wrote {a.out}")


def cmd_dump(a):
    reader = open_reader(a.pdf)
    fields = reader.get_fields() or {}
    n = 0
    for fid, f in fields.items():
        if f.get("/Kids") and f.get("/FT") != "/Btn":  # containers; radio groups keep /V on the parent
            continue
        v = f.get("/V")
        empty = v in (None, "", "/Off")
        if empty and not a.all:
            continue
        n += 1
        print(f"{fid} = {v!r}")
    print(f"{n} {'fields' if a.all else 'non-empty fields'}")


# ---------------------------------------------- non-fillable: bounding boxes
def get_bounding_box_messages(fields_json_stream):
    messages = []
    fields = json.load(fields_json_stream)
    messages.append(f"Read {len(fields['form_fields'])} fields")

    def intersect(r1, r2):
        disjoint_h = r1[0] >= r2[2] or r1[2] <= r2[0]
        disjoint_v = r1[1] >= r2[3] or r1[3] <= r2[1]
        return not (disjoint_h or disjoint_v)

    rects = []
    for f in fields["form_fields"]:
        rects.append((f["label_bounding_box"], "label", f))
        rects.append((f["entry_bounding_box"], "entry", f))
    has_error = False
    for i, (ri, ti, fi) in enumerate(rects):
        for rj, tj, fj in rects[i + 1:]:
            if fi["page_number"] == fj["page_number"] and intersect(ri, rj):
                has_error = True
                if fi is fj:
                    messages.append(f"FAILURE: intersection between label and entry bounding boxes for `{fi['description']}` ({ri}, {rj})")
                else:
                    messages.append(f"FAILURE: intersection between {ti} bounding box for `{fi['description']}` ({ri}) and {tj} bounding box for `{fj['description']}` ({rj})")
                if len(messages) >= 20:
                    messages.append("Aborting further checks; fix bounding boxes and try again")
                    return messages
        if ti == "entry" and "entry_text" in fi:
            font_size = fi["entry_text"].get("font_size", 14)
            height = ri[3] - ri[1]
            if height < font_size:
                has_error = True
                messages.append(f"FAILURE: entry bounding box height ({height}) for `{fi['description']}` is too short for the text content (font size: {font_size}). Increase the box height or decrease the font size.")
                if len(messages) >= 20:
                    messages.append("Aborting further checks; fix bounding boxes and try again")
                    return messages
    if not has_error:
        messages.append("SUCCESS: All bounding boxes are valid")
    return messages


def cmd_check_boxes(a):
    with open(a.fields) as f:
        msgs = get_bounding_box_messages(f)
    for m in msgs:
        print(m)
    if not msgs[-1].startswith("SUCCESS"):
        sys.exit(1)


def cmd_validation_image(a):
    from PIL import Image, ImageDraw
    with open(a.fields) as f:
        data = json.load(f)
    img = Image.open(a.in_png)
    draw = ImageDraw.Draw(img)
    n = 0
    for field in data["form_fields"]:
        if field["page_number"] == a.page:
            draw.rectangle(field["entry_bounding_box"], outline="red", width=2)
            draw.rectangle(field["label_bounding_box"], outline="blue", width=2)
            n += 2
    img.save(a.out_png)
    print(f"Created validation image at {a.out_png} with {n} bounding boxes")


def transform_coordinates(bbox, image_width, image_height, pdf_width, pdf_height):
    # Image: origin top-left, y down. PDF: origin bottom-left, y up.
    xs, ys = pdf_width / image_width, pdf_height / image_height
    return bbox[0] * xs, pdf_height - bbox[3] * ys, bbox[2] * xs, pdf_height - bbox[1] * ys


def cmd_annotate(a):
    from pypdf.annotations import FreeText
    with open(a.fields) as f:
        data = json.load(f)
    reader = open_reader(a.pdf)
    writer = PdfWriter()
    writer.append(reader)
    dims = {i + 1: [float(p.mediabox.width), float(p.mediabox.height)] for i, p in enumerate(reader.pages)}
    count = 0
    for field in data["form_fields"]:
        et = field.get("entry_text") or {}
        text = et.get("text")
        if not text:
            continue  # skip empty fields
        pn = field["page_number"]
        pinfo = next(p for p in data["pages"] if p["page_number"] == pn)
        rect = transform_coordinates(field["entry_bounding_box"], pinfo["image_width"], pinfo["image_height"], *dims[pn])
        # Font size/color is not honored by every viewer (pypdf issue #2084).
        ann = FreeText(text=text, rect=rect, font=et.get("font", "Arial"),
                       font_size=f"{et.get('font_size', 14)}pt", font_color=et.get("font_color", "000000"),
                       border_color=None, background_color=None)
        writer.add_annotation(page_number=pn - 1, annotation=ann)
        count += 1
    with open(a.out, "wb") as f:
        writer.write(f)
    print(f"Successfully filled PDF form and saved to {a.out}")
    print(f"Added {count} text annotations")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("check"); s.add_argument("pdf"); s.set_defaults(fn=cmd_check)
    s = sp.add_parser("extract"); s.add_argument("pdf"); s.add_argument("out"); s.set_defaults(fn=cmd_extract)
    s = sp.add_parser("render"); s.add_argument("pdf"); s.add_argument("out_dir")
    s.add_argument("--max-dim", type=int, default=1000); s.set_defaults(fn=cmd_render)
    s = sp.add_parser("fill"); s.add_argument("pdf"); s.add_argument("values"); s.add_argument("out")
    s.add_argument("--keep-xfa", action="store_true"); s.set_defaults(fn=cmd_fill)
    s = sp.add_parser("dump"); s.add_argument("pdf"); s.add_argument("--all", action="store_true"); s.set_defaults(fn=cmd_dump)
    s = sp.add_parser("check-boxes"); s.add_argument("fields"); s.set_defaults(fn=cmd_check_boxes)
    s = sp.add_parser("validation-image"); s.add_argument("page", type=int); s.add_argument("fields")
    s.add_argument("in_png"); s.add_argument("out_png"); s.set_defaults(fn=cmd_validation_image)
    s = sp.add_parser("annotate"); s.add_argument("pdf"); s.add_argument("fields"); s.add_argument("out")
    s.set_defaults(fn=cmd_annotate)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
