"""Step `annotate-form` (non-fillable forms): re-run the bounding-box check on the
fields.json object, then add each entry_text as a FreeText annotation at its entry
box (adapted from the pdf skill's fill_pdf_form_with_annotations.py).

stdin state: form_pdf_path, output_pdf_path, annotation_fields (fields.json object:
{"pages": [{page_number, image_width, image_height}], "form_fields": [...]}).
stdout: {"annotation_report": {output_pdf, annotations_added, bounding_box_check}}
Exits non-zero if any bounding boxes intersect or an entry box is shorter than its font.
"""
import io
import json

from pypdf import PdfWriter
from pypdf.annotations import FreeText

from check_bounding_boxes import get_bounding_box_messages
from pdf_form_lib import emit, fail, open_reader, read_stdin


def transform_coordinates(bbox, image_width, image_height, pdf_width, pdf_height):
    """Image coords (origin top-left, y down) -> PDF coords (origin bottom-left, y up)."""
    x_scale = pdf_width / image_width
    y_scale = pdf_height / image_height
    left = bbox[0] * x_scale
    right = bbox[2] * x_scale
    top = pdf_height - (bbox[1] * y_scale)
    bottom = pdf_height - (bbox[3] * y_scale)
    return left, bottom, right, top


def main():
    st = read_stdin().get("state", {})
    data = st["annotation_fields"]
    messages = get_bounding_box_messages(io.StringIO(json.dumps(data)))
    if any(m.startswith("FAILURE") for m in messages):
        fail("Bounding-box check failed; fix annotation_fields:\n" + "\n".join(messages))

    reader = open_reader(st["form_pdf_path"])
    writer = PdfWriter()
    writer.append(reader)
    dims = {i + 1: [float(p.mediabox.width), float(p.mediabox.height)] for i, p in enumerate(reader.pages)}
    added = 0
    for field in data["form_fields"]:
        entry = field.get("entry_text") or {}
        text = entry.get("text")
        if not text:
            continue
        page_num = field["page_number"]
        info = next(p for p in data["pages"] if p["page_number"] == page_num)
        rect = transform_coordinates(field["entry_bounding_box"], info["image_width"], info["image_height"], *dims[page_num])
        # Font size/color is not honored by every viewer (pypdf issue 2084).
        annotation = FreeText(
            text=text,
            rect=rect,
            font=entry.get("font", "Arial"),
            font_size=f"{entry.get('font_size', 14)}pt",
            font_color=entry.get("font_color", "000000"),
            border_color=None,
            background_color=None,
        )
        writer.add_annotation(page_number=page_num - 1, annotation=annotation)
        added += 1
    with open(st["output_pdf_path"], "wb") as f:
        writer.write(f)
    emit({"annotation_report": {"output_pdf": st["output_pdf_path"], "annotations_added": added,
                                "bounding_box_check": messages}})


if __name__ == "__main__":
    main()
