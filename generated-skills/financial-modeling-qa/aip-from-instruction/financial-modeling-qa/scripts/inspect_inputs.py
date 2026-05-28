#!/usr/bin/env python3
"""Inspect the financial-modeling-qa task inputs.

Dumps the background PDF as text and every sheet of the Excel workbook
(schema + head + dtypes) so the agent can decide how to map question
terms to columns before writing the computation.

Usage:
    python scripts/inspect_inputs.py
    python scripts/inspect_inputs.py --pdf /root/background.pdf --xlsx /root/data.xlsx
    python scripts/inspect_inputs.py --xlsx /root/data.xlsx --head 20

Exits 0 on success; non-zero if neither input exists or required
libraries are missing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def extract_pdf_text(path: Path) -> str:
    """Return the full text of a PDF, trying pypdf then PyPDF2 then pdftotext."""
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            PdfReader = None  # type: ignore

    if PdfReader is not None:
        reader = PdfReader(str(path))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)

    # Last-resort fallback: poppler's pdftotext binary, if installed.
    import shutil
    import subprocess

    if shutil.which("pdftotext"):
        out = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            check=True,
            capture_output=True,
            text=True,
        )
        return out.stdout

    raise RuntimeError(
        "No PDF reader available. Install pypdf "
        "(`pip install pypdf`) or poppler-utils (`apt install poppler-utils`)."
    )


def inspect_xlsx(path: Path, head_rows: int) -> None:
    """Print sheet names, shape, columns, dtypes, and head() for each sheet."""
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError(
            "pandas is required. Install with `pip install pandas openpyxl`."
        ) from exc

    xl = pd.ExcelFile(path)
    print(f"# Sheets ({len(xl.sheet_names)}): {xl.sheet_names}")
    for sheet in xl.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet)
        print(f"\n## Sheet: {sheet}")
        print(f"Shape: {df.shape}")
        print(f"Columns: {list(df.columns)}")
        print("Dtypes:")
        print(df.dtypes.to_string())
        print(f"\nHead ({min(head_rows, len(df))} rows):")
        with pd_display_options():
            print(df.head(head_rows).to_string())


def pd_display_options():
    """Context manager: widen pandas display for inspection output."""
    import contextlib

    import pandas as pd

    @contextlib.contextmanager
    def _ctx():
        with pd.option_context(
            "display.max_columns",
            None,
            "display.width",
            200,
            "display.max_colwidth",
            80,
        ):
            yield

    return _ctx()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", default="/root/background.pdf", type=Path)
    ap.add_argument("--xlsx", default="/root/data.xlsx", type=Path)
    ap.add_argument("--head", type=int, default=10, help="rows of head() to print per sheet")
    args = ap.parse_args()

    saw_any = False

    if args.pdf.exists():
        saw_any = True
        print("=" * 72)
        print(f"PDF: {args.pdf}")
        print("=" * 72)
        try:
            print(extract_pdf_text(args.pdf))
        except Exception as exc:
            print(f"[error reading PDF: {exc}]", file=sys.stderr)
    else:
        print(f"[skip] PDF not found at {args.pdf}", file=sys.stderr)

    if args.xlsx.exists():
        saw_any = True
        print("\n" + "=" * 72)
        print(f"XLSX: {args.xlsx}")
        print("=" * 72)
        try:
            inspect_xlsx(args.xlsx, args.head)
        except Exception as exc:
            print(f"[error reading XLSX: {exc}]", file=sys.stderr)
            return 2
    else:
        print(f"[skip] XLSX not found at {args.xlsx}", file=sys.stderr)

    if not saw_any:
        print("No inputs found at the documented paths.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
