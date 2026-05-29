#!/usr/bin/env python3
"""Fill {{PLACEHOLDER}} markers in a .docx template.

Handles every edge case the curated docx skill calls out:

  * Split runs: Word stores {{KEY}} across multiple XML runs (spellcheck,
    formatting changes). Replacement happens at the paragraph level — the
    full text is rebuilt and pushed into the first run, with later runs
    blanked so the first run's formatting is preserved.

  * Containers beyond doc.paragraphs: body, tables (recursively into nested
    tables), section headers, and section footers are all visited.

  * Conditional blocks {{IF_X}}...{{END_IF_X}} where X is a data key.
    - Truthy data[X]      -> markers stripped, content kept.
    - Falsy / missing X   -> the marker pair and everything between is dropped.
    Both same-paragraph and cross-paragraph conditional layouts are supported.

Truthy is liberal: bool True, non-zero numbers, and any of yes/y/true/t/1
(case-insensitive) for strings. Everything else, including missing keys,
is treated as falsy.

Usage:
    python fill_template.py \
        --template path/to/template.docx \
        --data path/to/data.json \
        --output path/to/filled.docx
"""

import argparse
import json
import re
import sys

from docx import Document

PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
IF_MARKER = re.compile(r"\{\{IF_([A-Z0-9_]+)\}\}")
END_IF_MARKER_TEMPLATE = "{{{{END_IF_{key}}}}}"

TRUTHY_STRINGS = {"yes", "y", "true", "t", "1"}


def is_truthy(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY_STRINGS
    return bool(value)


def _set_paragraph_text(para, new_text):
    """Push new_text into the first run, blank the rest. Preserves run 0's formatting."""
    if para.runs:
        para.runs[0].text = new_text
        for run in para.runs[1:]:
            run.text = ""
    else:
        para.text = new_text


def _resolve_same_paragraph_conditionals(text, data):
    """Resolve every {{IF_X}}...{{END_IF_X}} pair contained in a single paragraph."""
    while True:
        match = IF_MARKER.search(text)
        if not match:
            return text
        key = match.group(1)
        end_marker = END_IF_MARKER_TEMPLATE.format(key=key)
        end_idx = text.find(end_marker, match.end())
        if end_idx == -1:
            # Cross-paragraph case handled elsewhere; leave markers alone.
            return text
        if is_truthy(data.get(key)):
            text = (
                text[: match.start()]
                + text[match.end() : end_idx]
                + text[end_idx + len(end_marker) :]
            )
        else:
            text = text[: match.start()] + text[end_idx + len(end_marker) :]


def _substitute_placeholders(text, data):
    """Replace every {{KEY}} for which data has a value. Unknown keys are left intact."""
    def repl(match):
        key = match.group(1)
        return str(data[key]) if key in data else match.group(0)

    return PLACEHOLDER.sub(repl, text)


def _process_paragraph(para, data):
    text = para.text
    if not text:
        return
    new_text = _resolve_same_paragraph_conditionals(text, data)
    new_text = _substitute_placeholders(new_text, data)
    if new_text != text:
        _set_paragraph_text(para, new_text)


def _resolve_cross_paragraph_conditionals(paragraphs, data):
    """Handle {{IF_X}} ... {{END_IF_X}} spanning multiple paragraphs in `paragraphs`.

    Walks the list, matching each open IF to its closing END_IF. When truthy,
    the markers are stripped from the open/close paragraphs and content between
    is kept verbatim. When falsy, every paragraph from open through close
    (inclusive) is blanked.

    Same-paragraph IF/END_IF pairs are left for `_resolve_same_paragraph_conditionals`.
    """
    i = 0
    while i < len(paragraphs):
        para = paragraphs[i]
        match = IF_MARKER.search(para.text)
        if not match:
            i += 1
            continue
        key = match.group(1)
        end_marker = END_IF_MARKER_TEMPLATE.format(key=key)
        if end_marker in para.text:
            i += 1
            continue

        j = i + 1
        while j < len(paragraphs) and end_marker not in paragraphs[j].text:
            j += 1
        if j >= len(paragraphs):
            i += 1
            continue

        if is_truthy(data.get(key)):
            _set_paragraph_text(para, para.text.replace(match.group(0), ""))
            _set_paragraph_text(
                paragraphs[j], paragraphs[j].text.replace(end_marker, "")
            )
        else:
            for k in range(i, j + 1):
                _set_paragraph_text(paragraphs[k], "")
        i = j + 1


def _iter_paragraph_groups(doc):
    """Yield ordered paragraph lists per container so cross-paragraph IF/END_IF can be scoped."""
    yield list(doc.paragraphs)
    for table in doc.tables:
        yield from _iter_table_groups(table)
    for section in doc.sections:
        yield list(section.header.paragraphs)
        yield list(section.footer.paragraphs)


def _iter_table_groups(table):
    for row in table.rows:
        for cell in row.cells:
            yield list(cell.paragraphs)
            for nested in cell.tables:
                yield from _iter_table_groups(nested)


def fill(template_path, data, output_path):
    doc = Document(template_path)

    # Pass 1: resolve conditionals that span paragraphs within each container.
    for group in _iter_paragraph_groups(doc):
        _resolve_cross_paragraph_conditionals(group, data)

    # Pass 2: same-paragraph conditionals + placeholder substitution.
    for group in _iter_paragraph_groups(doc):
        for para in group:
            _process_paragraph(para, data)

    doc.save(output_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--template", required=True, help="Path to the .docx template")
    parser.add_argument(
        "--data", required=True, help="Path to a JSON file mapping keys to string values"
    )
    parser.add_argument("--output", required=True, help="Where to write the filled .docx")
    args = parser.parse_args()

    with open(args.data) as f:
        data = json.load(f)

    fill(args.template, data, args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
