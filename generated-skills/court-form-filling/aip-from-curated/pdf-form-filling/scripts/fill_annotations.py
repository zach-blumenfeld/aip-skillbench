"""fill-annotations step (non-fillable PDFs): place each entry_text as a FreeText annotation
at its entry_bounding_box, converting image pixels to PDF points (curated
fill_pdf_form_with_annotations.py).

stdin  {"currentState": {"pdf_path", "fields_spec", "output_pdf"}}
stdout {"annotations_added", "output_pdf"}

CLI: python fill_annotations.py <input.pdf> <fields.json> <output.pdf>
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pdf_forms as pf  # noqa: E402


def run(state, assets):
    out = pf.resolve_path(state["output_pdf"])
    n = pf.write_annotations(pf.resolve_path(state["pdf_path"]), state["fields_spec"], out)
    return {"annotations_added": n, "output_pdf": out}


if __name__ == "__main__":
    if len(sys.argv) == 4:
        with open(sys.argv[2]) as f:
            spec = json.load(f)
        r = run({"pdf_path": sys.argv[1], "fields_spec": spec, "output_pdf": sys.argv[3]}, {})
        print(f"Successfully filled PDF form and saved to {r['output_pdf']}\nAdded {r['annotations_added']} text annotations")
    else:
        state, assets = pf.read_step_input()
        pf.emit(run(state, assets))
