#!/usr/bin/env python3
"""Scan a filled .docx for leftover {{...}} placeholders.

Walks every paragraph the fill script can reach — body, tables (including
nested), section headers, section footers — and reports any tokens that
match ``{{[A-Z_][A-Z0-9_]*}}``.

Exit 0 = clean. Exit 1 = leftovers found (also listed on stdout as JSON).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Iterable

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

TOKEN_RE = re.compile(r"\{\{[A-Z_][A-Z0-9_]*\}\}")


def walk(doc) -> Iterable[Paragraph]:
    yield from doc.paragraphs

    def walk_table(table: Table) -> Iterable[Paragraph]:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs
                for nested in cell.tables:
                    yield from walk_table(nested)

    for table in doc.tables:
        yield from walk_table(table)
    for section in doc.sections:
        yield from section.header.paragraphs
        yield from section.footer.paragraphs


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--file", required=True)
    args = p.parse_args(argv)

    doc = Document(args.file)
    leftovers = sorted({m for para in walk(doc) for m in TOKEN_RE.findall(para.text)})
    print(json.dumps({"file": args.file, "ok": not leftovers, "remaining": leftovers}))
    return 0 if not leftovers else 1


if __name__ == "__main__":
    sys.exit(main())
