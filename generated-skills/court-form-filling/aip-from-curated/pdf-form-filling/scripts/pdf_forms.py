"""Shared helpers for the pdf-form-filling step scripts.

Adapted from the curated `pdf` skill's scripts (extract_form_field_info.py,
fill_fillable_fields.py, check_bounding_boxes.py, create_validation_image.py,
fill_pdf_form_with_annotations.py, convert_pdf_to_images.py). Needs only pypdf
(plus `cryptography` for AES-encrypted forms), Pillow (ships with reportlab) and
poppler-utils (`pdftoppm`, `pdftotext`) — all present in the task container.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html import unescape

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject


# ---------------------------------------------------------------- step I/O

def read_step_input():
    """Return (state, assets) from the AIP stdin payload."""
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    return payload.get("currentState", payload), payload.get("assets", {}) or {}


def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def resolve_path(path):
    """Scripts run with cwd = scripts/; resolve relative paths against the caller's cwd."""
    if not path or os.path.isabs(path):
        return path
    for base in (os.environ.get("AIP_CALLER_CWD"), os.environ.get("PWD")):
        if base:
            cand = os.path.join(base, path)
            if os.path.exists(cand) or os.path.isdir(os.path.dirname(cand) or "."):
                return os.path.abspath(cand)
    return os.path.abspath(path)


def load_profiles(assets):
    raw = assets.get("form-profiles")
    if raw is None:
        here = os.path.dirname(os.path.abspath(__file__))
        p = os.path.join(here, "..", "assets", "form-profiles.json")
        if os.path.exists(p):
            with open(p) as f:
                raw = f.read()
    if not raw:
        return {}
    return json.loads(raw) if isinstance(raw, str) else raw


def match_profile(field_ids, profiles):
    for name, prof in profiles.items():
        prefix = prof.get("match_prefix")
        if prefix and any(fid.startswith(prefix) for fid in field_ids):
            return name, prof
    return "", None


# ---------------------------------------------------------------- reading

def open_reader(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        if reader.is_encrypted:
            # Court forms are usually AES-encrypted with an empty user password
            # (owner restrictions only). pypdf needs `cryptography` for AES.
            reader.decrypt("")
        _ = len(reader.pages)
        return reader
    except Exception as e:  # noqa: BLE001
        if "cryptography" in str(e):
            raise SystemExit(
                f"{pdf_path} is AES-encrypted and pypdf needs the `cryptography` package to read it "
                f"(pip install cryptography). Original error: {e}"
            )
        raise


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
        flags = int(field.get("/Ff", 0) or 0)
        if flags & (1 << 16):  # pushbutton (Print / Save / Reset): never a value
            field_dict["type"] = "pushbutton"
            return field_dict
        field_dict["type"] = "checkbox"
        states = field.get("/_States_", [])
        if len(states) == 2:
            # "/Off" is the unchecked value; it can be first or second in /_States_.
            if "/Off" in states:
                field_dict["checked_value"] = states[0] if states[0] != "/Off" else states[1]
                field_dict["unchecked_value"] = "/Off"
            else:
                field_dict["checked_value"] = states[0]
                field_dict["unchecked_value"] = states[1]
                field_dict["warning"] = "Unexpected checkbox states; visually verify after checking."
        else:
            field_dict["type"] = "pushbutton"
    elif ft == "/Ch":
        field_dict["type"] = "choice"
        states = field.get("/_States_", [])
        field_dict["choice_options"] = [{"value": s[0], "text": s[1]} for s in states]
    else:
        field_dict["type"] = f"unknown ({ft})"
    return field_dict


def get_field_info(reader):
    """Fillable fields with page (1-based) and rect, sorted top-to-bottom per page.

    Same output shape as the curated extract_form_field_info.py, plus
    `pushbutton` type for buttons that must never be set.
    """
    fields = reader.get_fields() or {}
    field_info_by_id = {}
    possible_radio_names = set()
    for field_id, field in fields.items():
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
                field_info_by_id[field_id]["rect"] = [round(float(x), 1) for x in ann.get("/Rect")]
            elif field_id in possible_radio_names:
                try:
                    on_values = [v for v in ann["/AP"]["/N"] if v != "/Off"]
                except KeyError:
                    continue
                if len(on_values) == 1:
                    rect = [round(float(x), 1) for x in ann.get("/Rect")]
                    rf = radio_fields_by_id.setdefault(
                        field_id,
                        {"field_id": field_id, "type": "radio_group", "page": page_index + 1, "radio_options": []},
                    )
                    rf["radio_options"].append({"value": on_values[0], "rect": rect})

    # Some PDFs define fields with no widget annotation, so their location is unknown; skip them.
    located = [f for f in field_info_by_id.values() if "page" in f]
    get_field_info.unlocated = [f["field_id"] for f in field_info_by_id.values() if "page" not in f]

    def sort_key(f):
        rect = (f["radio_options"][0]["rect"] if "radio_options" in f else f.get("rect")) or [0, 0, 0, 0]
        return [f.get("page"), -rect[1], rect[0]]

    out = located + list(radio_fields_by_id.values())
    out.sort(key=sort_key)
    return out


def word_boxes(pdf_path):
    """{page: [(xMin, yMin, xMax, yMax, word)]} in top-down PDF points via pdftotext -bbox-layout."""
    if not shutil.which("pdftotext"):
        return {}
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "bbox.html")
        r = subprocess.run(["pdftotext", "-bbox-layout", pdf_path, out], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(out):
            return {}
        with open(out, encoding="utf-8", errors="replace") as f:
            html = f.read()
    pages = {}
    for pno, chunk in enumerate(re.split(r"<page\b", html)[1:], start=1):
        words = []
        for m in re.finditer(
            r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', chunk
        ):
            words.append((float(m[1]), float(m[2]), float(m[3]), float(m[4]), unescape(m[5])))
        pages[pno] = words
    return pages


def nearby_label(rect, page_height, words):
    """Printed text left of the field on the same line, plus caption text right under it."""
    if not rect or not words:
        return ""
    x0, y0, x1, y1 = rect
    top, bottom = page_height - y1, page_height - y0
    mid = (top + bottom) / 2
    left = [w for w in words if w[2] <= x0 + 2 and x0 - w[2] < 260 and w[1] - 3 <= mid <= w[3] + 3]
    left.sort(key=lambda w: w[0])
    # keep the run nearest to the field
    run = []
    for w in reversed(left):
        if run and run[0][0] - w[2] > 25:
            break
        run.insert(0, w)
    right = []
    if x1 - x0 < 16:  # checkbox/radio square: its caption is usually to the right
        right = [w for w in words if w[0] >= x1 - 2 and w[0] - x1 < 260 and w[1] - 3 <= mid <= w[3] + 3]
        right.sort(key=lambda w: w[0])
    below = [w for w in words if bottom - 2 <= w[1] <= bottom + 11 and w[0] >= x0 - 4 and w[2] <= x1 + 4]
    below.sort(key=lambda w: w[0])
    label = " ".join(w[4] for w in run[-10:])
    if right:
        label += (" | right: " if label else "right: ") + " ".join(w[4] for w in right[:12])
    if below:
        label += (" | under: " if label else "under: ") + " ".join(w[4] for w in below[:8])
    return label.strip()


# ---------------------------------------------------------------- rendering

def render_pages(pdf_path, out_dir, prefix="page", max_dim=1000, dpi=200):
    """PNG per page (curated convert_pdf_to_images.py, but via pdftoppm — pdf2image is not installed)."""
    os.makedirs(out_dir, exist_ok=True)
    if not shutil.which("pdftoppm"):
        return []
    tmp_prefix = os.path.join(out_dir, f"_{prefix}_raw")
    subprocess.run(["pdftoppm", "-png", "-r", str(dpi), pdf_path, tmp_prefix], check=True, capture_output=True)
    raws = sorted(
        (f for f in os.listdir(out_dir) if f.startswith(f"_{prefix}_raw")),
        key=lambda f: int(re.findall(r"(\d+)\.png$", f)[0]),
    )
    images = []
    try:
        from PIL import Image
    except ImportError:
        Image = None
    for i, fname in enumerate(raws, start=1):
        src = os.path.join(out_dir, fname)
        dst = os.path.join(out_dir, f"{prefix}_{i}.png")
        if Image:
            img = Image.open(src)
            w, h = img.size
            if w > max_dim or h > max_dim:
                s = min(max_dim / w, max_dim / h)
                img = img.resize((int(w * s), int(h * s)))
            img.save(dst)
            size = img.size
        else:
            os.replace(src, dst)
            size = (None, None)
        if os.path.exists(src):
            os.remove(src)
        images.append({"page": i, "path": dst, "width": size[0], "height": size[1]})
    return images


# ---------------------------------------------------------------- filling

def monkeypatch_pypdf_choice_bug():
    """pypdf joins /Opt of list boxes as strings; /Opt pairs make it throw. Return only values."""
    from pypdf.constants import FieldDictionaryAttributes
    from pypdf.generic import DictionaryObject

    if getattr(DictionaryObject, "_aip_patched", False):
        return
    original = DictionaryObject.get_inherited

    def patched(self, key, default=None):
        result = original(self, key, default)
        if key == FieldDictionaryAttributes.Opt and isinstance(result, list):
            if all(isinstance(v, list) and len(v) == 2 for v in result):
                result = [r[0] for r in result]
        return result

    DictionaryObject.get_inherited = patched
    DictionaryObject._aip_patched = True


def strip_xfa_and_usage_rights(writer):
    """XFA/AcroForm hybrids (all Judicial Council forms) keep a blank XFA copy that Acrobat
    renders instead of the AcroForm values; the Reader-extension signature (/Perms UR3)
    breaks once the file changes. Drop both so every viewer shows the filled AcroForm."""
    root = writer._root_object
    acro = root.get("/AcroForm")
    removed = []
    if acro is not None:
        acro = acro.get_object()
        if "/XFA" in acro:
            del acro["/XFA"]
            removed.append("XFA")
    if "/Perms" in root:
        del root["/Perms"]
        removed.append("Perms")
    return removed


def write_filled(input_pdf, fields_by_page, output_pdf):
    monkeypatch_pypdf_choice_bug()
    reader = open_reader(input_pdf)
    writer = PdfWriter(clone_from=reader)
    for page, values in fields_by_page.items():
        writer.update_page_form_field_values(writer.pages[page - 1], values, auto_regenerate=False)
    writer.set_need_appearances_writer(True)
    removed = strip_xfa_and_usage_rights(writer)
    os.makedirs(os.path.dirname(os.path.abspath(output_pdf)), exist_ok=True)
    with open(output_pdf, "wb") as f:
        writer.write(f)
    return removed


def read_values(pdf_path):
    reader = open_reader(pdf_path)
    out = {}
    for fid, f in (reader.get_fields() or {}).items():
        v = f.get("/V")
        if v is None:
            continue
        out[fid] = str(v)
    return out


# ---------------------------------------------------------------- annotations (non-fillable forms)

def rects_intersect(r1, r2):
    disjoint_h = r1[0] >= r2[2] or r1[2] <= r2[0]
    disjoint_v = r1[1] >= r2[3] or r1[3] <= r2[1]
    return not (disjoint_h or disjoint_v)


def bounding_box_messages(fields):
    """Curated check_bounding_boxes.py logic on an in-memory fields.json dict."""
    messages = [f"Read {len(fields['form_fields'])} fields"]
    rects = []
    for f in fields["form_fields"]:
        rects.append((f["label_bounding_box"], "label", f))
        rects.append((f["entry_bounding_box"], "entry", f))
    has_error = False
    for i, (ri, ti, fi) in enumerate(rects):
        for j in range(i + 1, len(rects)):
            rj, tj, fj = rects[j]
            if fi["page_number"] == fj["page_number"] and rects_intersect(ri, rj):
                has_error = True
                if fi is fj:
                    messages.append(
                        f"FAILURE: intersection between label and entry bounding boxes for `{fi['description']}` ({ri}, {rj})"
                    )
                else:
                    messages.append(
                        f"FAILURE: intersection between {ti} bounding box for `{fi['description']}` ({ri}) and {tj} bounding box for `{fj['description']}` ({rj})"
                    )
                if len(messages) >= 20:
                    messages.append("Aborting further checks; fix bounding boxes and try again")
                    return messages, False
        if ti == "entry" and "entry_text" in fi:
            font_size = fi["entry_text"].get("font_size", 14)
            h = ri[3] - ri[1]
            if h < font_size:
                has_error = True
                messages.append(
                    f"FAILURE: entry bounding box height ({h}) for `{fi['description']}` is too short for the text content (font size: {font_size}). Increase the box height or decrease the font size."
                )
                if len(messages) >= 20:
                    messages.append("Aborting further checks; fix bounding boxes and try again")
                    return messages, False
    if not has_error:
        messages.append("SUCCESS: All bounding boxes are valid")
    return messages, not has_error


def draw_validation_image(page_number, fields, input_path, output_path):
    from PIL import Image, ImageDraw

    img = Image.open(input_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    n = 0
    for field in fields["form_fields"]:
        if field["page_number"] == page_number:
            draw.rectangle(field["entry_bounding_box"], outline="red", width=2)
            draw.rectangle(field["label_bounding_box"], outline="blue", width=2)
            n += 2
    img.save(output_path)
    return n


def transform_coordinates(bbox, image_width, image_height, pdf_width, pdf_height):
    """Image coords (top-left origin) -> PDF coords (bottom-left origin)."""
    xs, ys = pdf_width / image_width, pdf_height / image_height
    return bbox[0] * xs, pdf_height - bbox[3] * ys, bbox[2] * xs, pdf_height - bbox[1] * ys


def write_annotations(input_pdf, fields, output_pdf):
    from pypdf.annotations import FreeText

    reader = open_reader(input_pdf)
    writer = PdfWriter()
    writer.append(reader)
    dims = {i + 1: (float(p.mediabox.width), float(p.mediabox.height)) for i, p in enumerate(reader.pages)}
    added = 0
    for field in fields["form_fields"]:
        et = field.get("entry_text") or {}
        text = et.get("text")
        if not text:
            continue
        pno = field["page_number"]
        pinfo = next(p for p in fields["pages"] if p["page_number"] == pno)
        rect = transform_coordinates(
            field["entry_bounding_box"], pinfo["image_width"], pinfo["image_height"], *dims[pno]
        )
        ann = FreeText(
            text=text,
            rect=rect,
            font=et.get("font", "Arial"),
            font_size=f"{et.get('font_size', 14)}pt",
            font_color=et.get("font_color", "000000"),
            border_color=None,
            background_color=None,
        )
        writer.add_annotation(page_number=pno - 1, annotation=ann)
        added += 1
    os.makedirs(os.path.dirname(os.path.abspath(output_pdf)), exist_ok=True)
    with open(output_pdf, "wb") as f:
        writer.write(f)
    return added
