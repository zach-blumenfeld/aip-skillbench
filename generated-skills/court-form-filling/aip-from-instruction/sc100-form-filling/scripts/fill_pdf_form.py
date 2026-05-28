#!/usr/bin/env python3
"""Fill an AcroForm PDF from a JSON field-mapping file.

Usage:
    python fill_pdf_form.py <input.pdf> <mapping.json> <output.pdf>

mapping.json is a flat object: {"<field name>": <value>, ...}

Value conventions:
    - Text field (/Tx)    -> string. Use "" or omit to leave blank.
    - Checkbox (/Btn)     -> string matching one of /AP /N option keys
                              (commonly "/Yes" or "Yes" — the script tries
                              both with and without the leading slash).
    - Choice (/Ch)        -> string (selected option label).

Fields not present in mapping.json are left untouched (blank, in the
typical case where the input is a blank form). Fields in mapping.json
whose value is an empty string are also left untouched — explicit way
to "leave blank."

The script preserves the AcroForm so the result is still a fillable PDF
(NeedAppearances=true) — viewers regenerate field appearances on open.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import BooleanObject, NameObject
except ImportError:
    print(
        "ERROR: pypdf not installed. Install with: pip install pypdf",
        file=sys.stderr,
    )
    sys.exit(2)


def _normalize_checkbox_value(value: str) -> str:
    """Map a checkbox value to the AcroForm export-value form.

    pypdf accepts the bare name ('Yes', 'Off'); some forms expect a
    leading slash. Stripping the slash is the safer normalization.
    """
    return value.lstrip("/")


def load_mapping(path: Path) -> dict[str, str]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("mapping JSON must be a top-level object")
    cleaned: dict[str, str] = {}
    for k, v in raw.items():
        if v is None or v == "":
            continue  # leave blank
        if not isinstance(v, (str, int, float, bool)):
            raise ValueError(
                f"value for field {k!r} must be string/number/bool, got {type(v).__name__}"
            )
        cleaned[k] = str(v)
    return cleaned


def fill_pdf(input_pdf: Path, mapping: dict[str, str], output_pdf: Path) -> dict:
    reader = PdfReader(str(input_pdf))
    writer = PdfWriter(clone_from=reader)

    # Get the form fields known to the document so we can warn about
    # mappings that target nonexistent fields.
    known = set((reader.get_fields() or {}).keys())
    unknown = sorted(k for k in mapping.keys() if k not in known)

    # Detect checkbox fields so we can normalize their values.
    field_types: dict[str, str] = {}
    for fname, field in (reader.get_fields() or {}).items():
        field_types[fname] = str(field.get("/FT", ""))

    # Apply checkbox normalization
    apply_map: dict[str, str] = {}
    for k, v in mapping.items():
        if field_types.get(k) == "/Btn":
            apply_map[k] = _normalize_checkbox_value(v)
        else:
            apply_map[k] = v

    # Fill on each page that has annotations from the form.
    pages_updated = 0
    for page in writer.pages:
        if "/Annots" not in page:
            continue
        writer.update_page_form_field_values(page, apply_map)
        pages_updated += 1

    # Ensure viewers regenerate the visual appearances for our new values.
    if "/AcroForm" in writer._root_object:
        writer._root_object["/AcroForm"][NameObject("/NeedAppearances")] = BooleanObject(True)

    with open(output_pdf, "wb") as fh:
        writer.write(fh)

    return {
        "filled": len(apply_map),
        "unknown_fields": unknown,
        "pages_updated": pages_updated,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill an AcroForm PDF from a JSON mapping.")
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("mapping_json", type=Path)
    parser.add_argument("output_pdf", type=Path)
    args = parser.parse_args()

    if not args.input_pdf.exists():
        print(f"ERROR: input PDF not found: {args.input_pdf}", file=sys.stderr)
        return 1
    if not args.mapping_json.exists():
        print(f"ERROR: mapping JSON not found: {args.mapping_json}", file=sys.stderr)
        return 1

    try:
        mapping = load_mapping(args.mapping_json)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: bad mapping JSON: {exc}", file=sys.stderr)
        return 1

    result = fill_pdf(args.input_pdf, mapping, args.output_pdf)

    print(f"Wrote {args.output_pdf}")
    print(f"  filled fields: {result['filled']}")
    print(f"  pages updated: {result['pages_updated']}")
    if result["unknown_fields"]:
        print(
            "WARNING: these mapping keys are not fields on the form "
            "(typos? leave-blank intent?):",
            file=sys.stderr,
        )
        for k in result["unknown_fields"]:
            print(f"  - {k}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
