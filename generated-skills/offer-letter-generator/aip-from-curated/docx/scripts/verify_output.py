#!/usr/bin/env python3
"""Verify a filled .docx has no leftover {{...}} placeholder markers.

Walks body, tables (recursively), and section headers/footers. Reports any
markers still present so the operator can fix the data file or the template.

Usage:
    python verify_output.py --output path/to/filled.docx

Exit codes:
    0  no leftover markers
    1  leftovers found (listed on stderr)
"""

import argparse
import re
import sys

from docx import Document

LEFTOVER = re.compile(r"\{\{[^{}]+\}\}")


def iter_paragraphs(doc):
    for para in doc.paragraphs:
        yield para
    for table in doc.tables:
        yield from _iter_table_paragraphs(table)
    for section in doc.sections:
        for para in section.header.paragraphs:
            yield para
        for para in section.footer.paragraphs:
            yield para


def _iter_table_paragraphs(table):
    for row in table.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                yield para
            for nested in cell.tables:
                yield from _iter_table_paragraphs(nested)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", required=True, help="Path to the filled .docx")
    args = parser.parse_args()

    doc = Document(args.output)
    leftovers = []
    for para in iter_paragraphs(doc):
        leftovers.extend(LEFTOVER.findall(para.text))

    if leftovers:
        print("LEFTOVER PLACEHOLDERS:", file=sys.stderr)
        for marker in leftovers:
            print(f"  {marker}", file=sys.stderr)
        return 1

    print("OK: no leftover placeholders")
    return 0


if __name__ == "__main__":
    sys.exit(main())
