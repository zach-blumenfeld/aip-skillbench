"""Step `verify-output`: re-open the saved .docx and prove it is complete.

Fails when any part (body, nested tables, headers, footers, notes) still holds
"{{", "}}", or an IF_/END_IF_ marker, or when a value the template should carry is
absent from the document text.

stdin  {"currentState": {template_path, output_path, values, conditions}, ...}
stdout {verify_status, problems, values_not_found, document_text}
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
    if not os.path.isfile(output):
        dt.emit({"verify_status": "failed", "problems": [{"issue": "output file missing", "path": output}],
                 "values_not_found": [], "document_text": ""})
        return
    conditions = {k: bool(v) if isinstance(v, bool) else bool(dt.truthiness(v)) for k, v in state["conditions"].items()}
    dry = Document(template)
    dt.apply_conditionals(dry, conditions)
    expected = sorted({o["key"] for o in dt.scan(dry)[0] if not o["key"].startswith(("IF_", "END_IF_"))})
    problems, not_found, text = dt.verify(output, state["values"], expected)
    not_found_keys = [k for k in expected if k not in state["values"]]
    for k in not_found_keys:
        problems.append({"issue": "no value supplied", "key": k})
    dt.emit({
        "verify_status": "verified" if not problems and not not_found else "failed",
        "problems": problems,
        "values_not_found": not_found,
        "expected_keys": expected,
        "document_text": text[:6000],
    })


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        dt.emit({"error": "%s: %s" % (type(e).__name__, e), "trace": traceback.format_exc(limit=3)})
        sys.exit(1)
