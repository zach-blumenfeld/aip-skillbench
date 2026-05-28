#!/usr/bin/env python3
"""Inspect an AcroForm PDF and print every fillable field.

Usage:
    python inspect_pdf_form.py <input.pdf> [--json]

Without --json: prints one line per field as `<name>\t<type>\t<current_value>`.
With --json: emits a JSON array of {name, type, value, options, flags} —
suitable for feeding into a planning step before filling.

Field types reported:
    /Tx  -> text
    /Btn -> button (checkbox / radio / pushbutton — see flags + /Kids)
    /Ch  -> choice (combo / list)
    /Sig -> signature

For /Btn fields, `options` lists the appearance state values from /AP /N
(e.g., "/Yes", "/Off") so the caller knows what to write to check a box.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from pypdf import PdfReader
    from pypdf.generic import IndirectObject, NameObject
except ImportError:
    print(
        "ERROR: pypdf not installed. Install with: pip install pypdf",
        file=sys.stderr,
    )
    sys.exit(2)


def _resolve(obj):
    if isinstance(obj, IndirectObject):
        return obj.get_object()
    return obj


def _appearance_states(field) -> list[str]:
    """Return the /AP /N keys for a button field — the values that 'check' the box."""
    states: list[str] = []
    ap = _resolve(field.get("/AP"))
    if ap is None:
        return states
    n = _resolve(ap.get("/N"))
    if n is None:
        return states
    for key in n.keys():
        states.append(str(key))
    return states


def inspect_fields(pdf_path: Path) -> list[dict]:
    reader = PdfReader(str(pdf_path))
    fields = reader.get_fields() or {}

    out: list[dict] = []
    for name, field in fields.items():
        field_obj = _resolve(field)
        ftype = str(field_obj.get("/FT", ""))
        value = field_obj.get("/V")
        if value is not None:
            value = str(value)
        flags = int(field_obj.get("/Ff", 0) or 0)
        options = _appearance_states(field_obj) if ftype == "/Btn" else []
        out.append(
            {
                "name": name,
                "type": ftype,
                "value": value,
                "flags": flags,
                "options": options,
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect AcroForm fields in a PDF.")
    parser.add_argument("pdf", type=Path, help="path to input PDF")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of TSV")
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"ERROR: file not found: {args.pdf}", file=sys.stderr)
        return 1

    fields = inspect_fields(args.pdf)

    if args.json:
        print(json.dumps(fields, indent=2))
    else:
        for f in fields:
            opts = f"\toptions={','.join(f['options'])}" if f["options"] else ""
            val = f["value"] if f["value"] is not None else ""
            print(f"{f['name']}\t{f['type']}\t{val}{opts}")

    print(f"\n{len(fields)} field(s) found in {args.pdf}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
