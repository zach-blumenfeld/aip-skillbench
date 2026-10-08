"""check-boxes step (non-fillable PDFs): validate the fields.json plan and draw validation images.

Automated check (curated check_bounding_boxes.py): no label/entry box intersects another
box on the same page; entry boxes are at least as tall as their font size. Then draws red
(entry) and blue (label) rectangles on each page image (curated create_validation_image.py).

stdin  {"currentState": {"fields_spec": <fields.json object>, "page_images", "work_dir"}}
stdout {"boxes_ok", "box_messages", "validation_images", "fields_json_path"}

CLI: python check_boxes.py <fields.json>
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pdf_forms as pf  # noqa: E402


def check(state, assets):
    spec = state["fields_spec"]
    work_dir = pf.resolve_path(state.get("work_dir") or ".")
    os.makedirs(work_dir, exist_ok=True)
    messages, ok = pf.bounding_box_messages(spec)
    path = os.path.join(work_dir, "fields.json")
    with open(path, "w") as f:
        json.dump(spec, f, indent=2)
    images = []
    for im in state.get("page_images") or []:
        out = os.path.join(work_dir, "validation", f"validation_page_{im['page']}.png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        if any(f["page_number"] == im["page"] for f in spec["form_fields"]):
            n = pf.draw_validation_image(im["page"], spec, im["path"], out)
            images.append(out)
            messages.append(f"Created validation image at {out} with {n} bounding boxes")
    return {"boxes_ok": ok, "box_messages": messages, "validation_images": images, "fields_json_path": path}


if __name__ == "__main__":
    if len(sys.argv) == 2:
        with open(sys.argv[1]) as f:
            msgs, _ = pf.bounding_box_messages(json.load(f))
        print("\n".join(msgs))
    else:
        state, assets = pf.read_step_input()
        pf.emit(check(state, assets))
