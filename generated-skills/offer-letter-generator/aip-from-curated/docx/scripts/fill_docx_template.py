#!/usr/bin/env python3
"""Fill a Word (.docx) template with values from a JSON data file.

Handles the four gotchas that break naive python-docx replacement:

  1. Split placeholders. Word stores ``{{CANDIDATE_NAME}}`` across multiple
     <w:r> runs (e.g. ``{{CANDI`` + ``DATE_NAME}}``). Run-level ``in`` checks
     miss them. We read each paragraph's ``.text`` (which joins runs),
     compute the new text, then write the result back into ``runs[0].text``
     and blank the trailing runs — preserving the first run's formatting.

  2. Headers and footers. They live on ``doc.sections[i].header`` and
     ``.footer``, not in ``doc.paragraphs``. Walk them separately.

  3. Nested tables. A ``cell.tables`` list may itself contain cells with
     tables. Recurse.

  4. Conditional blocks. ``{{IF_X}}...{{END_IF_X}}`` is kept (markers
     stripped) or dropped (block emptied) based on either an explicit
     ``--conditions`` map or auto-resolution from the data:
        - ``data[X]`` truthy
        - else ``data[X + "_PACKAGE"]`` / ``_ENABLED`` / ``_INCLUDED`` truthy
        - else default to KEEP (markers stripped, content retained).

     Inline conditionals (markers in the same paragraph) are handled in the
     replacement pass. Cross-paragraph blocks are resolved in a second pass
     that walks paragraph lists with a state machine.

Truthiness: booleans and numbers use their native truthiness; strings are
truthy unless they are in ``{"", "no", "false", "n", "0"}`` (case-insensitive).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

PLACEHOLDER_RE = re.compile(r"\{\{([A-Z_][A-Z0-9_]*)\}\}")
IF_RE = re.compile(r"\{\{IF_([A-Z_][A-Z0-9_]*)\}\}")
ENDIF_RE = re.compile(r"\{\{END_IF_([A-Z_][A-Z0-9_]*)\}\}")

FALSY_STRINGS = {"", "no", "false", "n", "0"}


def is_truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if value is None:
        return False
    return str(value).strip().lower() not in FALSY_STRINGS


def resolve_conditions(full_text: str, data: dict, explicit: dict | None) -> dict:
    explicit = explicit or {}
    resolved: dict[str, bool] = {}
    for tag in set(IF_RE.findall(full_text)):
        if tag in explicit:
            resolved[tag] = bool(explicit[tag])
            continue
        if tag in data:
            resolved[tag] = is_truthy(data[tag])
            continue
        for suffix in ("_PACKAGE", "_ENABLED", "_INCLUDED"):
            key = tag + suffix
            if key in data:
                resolved[tag] = is_truthy(data[key])
                break
        else:
            resolved[tag] = True
    return resolved


def rebuild_paragraph(para: Paragraph, new_text: str) -> None:
    """Write ``new_text`` to ``runs[0]`` and blank the rest, keeping formatting."""
    if not para.runs:
        # Empty paragraph: add a run so we can carry text.
        para.add_run(new_text)
        return
    para.runs[0].text = new_text
    for run in para.runs[1:]:
        run.text = ""


def apply_inline_conditionals(text: str, conditions: dict) -> str:
    """Resolve IF/END_IF blocks that open and close within the same string.

    Leaves unmatched markers untouched so the cross-paragraph pass can handle
    them.
    """
    out = text
    while True:
        m_if = IF_RE.search(out)
        if not m_if:
            return out
        tag = m_if.group(1)
        m_end = ENDIF_RE.search(out, m_if.end())
        if not m_end or m_end.group(1) != tag:
            return out
        keep = conditions.get(tag, True)
        if keep:
            out = out[: m_if.start()] + out[m_if.end() : m_end.start()] + out[m_end.end() :]
        else:
            out = out[: m_if.start()] + out[m_end.end() :]


def replace_placeholders(text: str, data: dict) -> str:
    def sub(match: re.Match) -> str:
        key = match.group(1)
        if key in data:
            return str(data[key])
        return match.group(0)

    return PLACEHOLDER_RE.sub(sub, text)


def process_paragraph(para: Paragraph, data: dict, conditions: dict) -> None:
    text = para.text
    if "{{" not in text:
        return
    new_text = apply_inline_conditionals(text, conditions)
    new_text = replace_placeholders(new_text, data)
    if new_text != text:
        rebuild_paragraph(para, new_text)


def process_table(table: Table, data: dict, conditions: dict) -> None:
    for row in table.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                process_paragraph(para, data, conditions)
            for nested in cell.tables:
                process_table(nested, data, conditions)


def strip_cross_paragraph_blocks(paragraphs: Iterable[Paragraph], conditions: dict) -> None:
    """Handle ``{{IF_X}}`` and ``{{END_IF_X}}`` that span paragraphs.

    Strips the markers from their paragraphs; when ``keep`` is false, empties
    the intervening paragraphs as well. Paragraphs without markers are left
    untouched.
    """
    paragraphs = list(paragraphs)
    state: tuple[str, bool] | None = None
    for para in paragraphs:
        text = para.text
        if state is None:
            m_if = IF_RE.search(text)
            if not m_if:
                continue
            tag = m_if.group(1)
            keep = conditions.get(tag, True)
            stripped = text[: m_if.start()] + text[m_if.end() :]
            rebuild_paragraph(para, "" if not keep else stripped)
            state = (tag, keep)
        else:
            tag, keep = state
            m_end = ENDIF_RE.search(text)
            if m_end and m_end.group(1) == tag:
                stripped = text[: m_end.start()] + text[m_end.end() :]
                rebuild_paragraph(para, "" if not keep else stripped)
                state = None
            elif not keep:
                rebuild_paragraph(para, "")
            # else: keep path — content already had placeholders replaced.


def walk_all_paragraph_lists(doc) -> Iterable[list[Paragraph]]:
    yield list(doc.paragraphs)

    def walk_table(table: Table):
        for row in table.rows:
            for cell in row.cells:
                yield list(cell.paragraphs)
                for nested in cell.tables:
                    yield from walk_table(nested)

    for table in doc.tables:
        yield from walk_table(table)
    for section in doc.sections:
        yield list(section.header.paragraphs)
        yield list(section.footer.paragraphs)


def gather_all_text(doc) -> str:
    return "\n".join(p.text for paras in walk_all_paragraph_lists(doc) for p in paras)


def fill(doc, data: dict, explicit_conditions: dict | None) -> dict:
    full_text = gather_all_text(doc)
    conditions = resolve_conditions(full_text, data, explicit_conditions)

    for para in doc.paragraphs:
        process_paragraph(para, data, conditions)
    for table in doc.tables:
        process_table(table, data, conditions)
    for section in doc.sections:
        for para in section.header.paragraphs:
            process_paragraph(para, data, conditions)
        for para in section.footer.paragraphs:
            process_paragraph(para, data, conditions)

    for paragraphs in walk_all_paragraph_lists(doc):
        strip_cross_paragraph_blocks(paragraphs, conditions)

    return conditions


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--template", required=True, help="Path to the .docx template.")
    p.add_argument("--data", required=True, help="Path to a JSON file of replacement values.")
    p.add_argument("--output", required=True, help="Where to write the filled .docx.")
    p.add_argument(
        "--conditions",
        default=None,
        help='Optional JSON object mapping IF tags to booleans, e.g. \'{"RELOCATION": true}\'. '
        "Overrides auto-resolution.",
    )
    args = p.parse_args(argv)

    with open(args.data) as f:
        data = json.load(f)

    explicit = json.loads(args.conditions) if args.conditions else None
    if explicit is not None and not isinstance(explicit, dict):
        print("--conditions must be a JSON object", file=sys.stderr)
        return 2

    doc = Document(args.template)
    conditions = fill(doc, data, explicit)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)

    print(json.dumps({"output": str(out_path), "resolved_conditions": conditions}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
