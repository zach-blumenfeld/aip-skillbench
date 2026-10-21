#!/usr/bin/env python3
"""Dump the text of a case-study background PDF, page by page.

Requires: Python >= 3.8, pypdf (pip name `pypdf`, tested with 5.1.0).

Usage:
    python scripts/extract_pdf_text.py /root/background.pdf [out.txt]

pypdf prints "Ignoring wrong pointing object" warnings on some ModelOff PDFs;
they are harmless and are silenced here. A page that yields no text is
reported so you know the PDF may be scanned (no OCR is available in the
task container -- fall back to reading the rules from the question itself).
"""
import logging
import sys

try:
    from pypdf import PdfReader
except ImportError:
    sys.exit("pypdf is not installed. Install it (pip install pypdf) or read the PDF another way.")

logging.getLogger("pypdf").setLevel(logging.ERROR)


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit("Usage: python scripts/extract_pdf_text.py <file.pdf> [out.txt]")
    reader = PdfReader(sys.argv[1])
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as e:
            sys.exit(f"PDF is encrypted and could not be opened with an empty password: {e}")
    chunks = []
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        if not text.strip():
            text = "[no extractable text on this page -- possibly scanned]"
        chunks.append(f"===== Page {i} of {len(reader.pages)} =====\n{text}")
    out = "\n\n".join(chunks)
    if len(sys.argv) == 3:
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            f.write(out)
    print(out)


if __name__ == "__main__":
    main()
