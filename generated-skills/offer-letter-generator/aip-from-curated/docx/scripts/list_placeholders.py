#!/usr/bin/env python3
"""List distinct {{PLACEHOLDER}} keys in a .docx template.

Walks body paragraphs, tables (including nested), and section headers/footers,
joining each paragraph's text before matching so placeholders split across XML
runs are still found.

Usage:
    python list_placeholders.py --template path/to/template.docx
"""

import argparse
import re
import sys

from docx import Document

PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


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
    parser.add_argument("--template", required=True, help="Path to the .docx template")
    args = parser.parse_args()

    doc = Document(args.template)
    keys = set()
    for para in iter_paragraphs(doc):
        keys.update(PLACEHOLDER.findall(para.text))

    for key in sorted(keys):
        print(key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
