"""Step `fill`: write the filled document.

Order matters: conditional blocks first (so placeholders inside a removed block are
removed with it), then every {{KEY}} in every part, then save to output_path.

stdin  {"currentState": {template_path, output_path, values, conditions}, ...}
stdout {output_path, replaced, unresolved, conditional_report}
"""
import os
import sys
import traceback

import docx_template as dt
from docx import Document


def main():
    state = dt.read_stdin()
    template = dt.resolve_path(state["template_path"])
    output = dt.resolve_path(state["output_path"])
    if os.path.abspath(output) == os.path.abspath(template):
        raise ValueError("refusing to overwrite the template; choose a different output_path")
    conditions = {k: bool(v) if isinstance(v, bool) else bool(dt.truthiness(v)) for k, v in state["conditions"].items()}
    doc = Document(template)
    cond_report = dt.apply_conditionals(doc, conditions)
    replaced, unresolved = dt.apply_placeholders(doc, state["values"])
    dt.flush_parts(doc)
    parent = os.path.dirname(output)
    if parent:
        os.makedirs(parent, exist_ok=True)
    doc.save(output)
    dt.emit({
        "output_path": output,
        "replaced": replaced,
        "unresolved": unresolved,
        "conditional_report": cond_report,
        "inspect_status": "resolved",
        "issues": [],
    })


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        dt.emit({"error": "%s: %s" % (type(e).__name__, e), "trace": traceback.format_exc(limit=3)})
        sys.exit(1)
