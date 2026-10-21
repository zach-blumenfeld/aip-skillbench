"""Steps `fill-sc100` and `fill-generic`: write the field values into the blank form,
save the output PDF, and verify it by reading it back.

stdin state: form_pdf_path, output_pdf_path, and either sc100_field_values or
generic_field_values (a list of {"field_id", "value", optional "page"}).
stdout: {"sc100_fill_report": {...}} or {"generic_fill_report": {...}} matching the input.
Exits non-zero (and writes the reasons to stderr) on an unknown field id, a wrong
page, an invalid checkbox/radio/choice value, or a read-back mismatch.
"""
import os

from pdf_form_lib import emit, fail, fill_and_verify, read_stdin


def main():
    st = read_stdin().get("state", {})
    if "sc100_field_values" in st:
        values, out_key = st["sc100_field_values"], "sc100_fill_report"
    elif "generic_field_values" in st:
        values, out_key = st["generic_field_values"], "generic_fill_report"
    else:
        fail("state needs sc100_field_values or generic_field_values")
    out_path = st["output_pdf_path"]
    parent = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(parent, exist_ok=True)
    report = fill_and_verify(st["form_pdf_path"], values, out_path)
    emit({out_key: report})


if __name__ == "__main__":
    main()
