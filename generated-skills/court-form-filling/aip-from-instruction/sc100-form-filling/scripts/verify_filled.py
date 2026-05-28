#!/usr/bin/env python3
"""Verify a filled SC-100 (or any AcroForm) PDF.

Prints, for every field, whether it is filled and with what value, so an
agent can confirm intended fields were written and intended-blank fields
remain blank.

Usage:
    python verify_filled.py <filled.pdf> [--expected mapping.json]

With --expected: cross-checks that every key in mapping.json appears
with the expected value in the filled PDF, and that no other field
was written. Exits 1 on mismatch.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    print("ERROR: pypdf not installed. pip install pypdf", file=sys.stderr)
    sys.exit(2)


def field_values(pdf_path: Path) -> dict[str, str]:
    reader = PdfReader(str(pdf_path))
    out: dict[str, str] = {}
    for name, field in (reader.get_fields() or {}).items():
        v = field.get("/V")
        out[name] = "" if v is None else str(v)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify field values in a filled AcroForm PDF.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--expected", type=Path, help="optional mapping JSON to diff against")
    args = parser.parse_args()

    values = field_values(args.pdf)
    print(f"{len(values)} field(s) in {args.pdf}")
    filled = {k: v for k, v in values.items() if v not in ("", "/Off")}
    print(f"{len(filled)} filled field(s):")
    for k, v in filled.items():
        print(f"  {k} = {v!r}")

    if args.expected is None:
        return 0

    expected = json.loads(args.expected.read_text())
    expected = {k: ("" if v is None else str(v)) for k, v in expected.items()}

    mismatches: list[str] = []
    for k, want in expected.items():
        if want == "":
            continue
        got = values.get(k, "<missing field>")
        # Checkbox: expected "Yes" matches actual "/Yes" or "Yes"
        if got.lstrip("/") != want.lstrip("/"):
            mismatches.append(f"  {k}: expected {want!r}, got {got!r}")

    extra_filled: list[str] = []
    for k, v in filled.items():
        if k not in expected or expected[k] == "":
            extra_filled.append(f"  {k} = {v!r}")

    if mismatches:
        print("\nFAIL — mismatched fields:", file=sys.stderr)
        for line in mismatches:
            print(line, file=sys.stderr)
    if extra_filled:
        print("\nWARNING — fields filled but not in expected mapping:", file=sys.stderr)
        for line in extra_filled:
            print(line, file=sys.stderr)

    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
