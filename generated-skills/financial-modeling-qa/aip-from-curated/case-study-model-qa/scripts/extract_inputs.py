#!/usr/bin/env python3
"""Read the case-study PDF as text and profile every sheet of the data workbook.

stdin:  {"currentState": {"pdf_path", "xlsx_path", ...}, "assets": {}, "expects": [...]}
stdout: {"pdf_text", "workbook_profile", "pdf_path", "xlsx_path"}

The profile exists to surface layout traps before any modelling: blank rows inside
a data block, records displaced outside the block, numbers stored as text, formulas.
Needs only openpyxl + pypdf (both in the task container).
"""
import json
import os
import re
import sys
import warnings

warnings.filterwarnings("ignore")


def fail(msg):
    print(json.dumps({"error": msg}))
    sys.exit(1)


def resolve(path, kind):
    if not path:
        fail(f"{kind} is empty")
    cands = [path, os.path.join("/root", os.path.basename(path)),
             os.path.join(os.getcwd(), os.path.basename(path))]
    for c in cands:
        if os.path.isabs(c) and os.path.exists(c):
            return c
    fail(f"{kind} not found: {path!r} (pass an absolute path; also tried /root/<name>)")


def pdf_text(path):
    try:
        import logging
        logging.getLogger("pypdf").setLevel(logging.ERROR)
        from pypdf import PdfReader
        r = PdfReader(path)
        if r.is_encrypted:
            try:
                r.decrypt("")
            except Exception:
                pass
        parts = []
        for i, p in enumerate(r.pages):
            parts.append(f"--- page {i + 1} ---\n{(p.extract_text() or '').strip()}")
        text = "\n".join(parts)
        if len(text.replace("-", "").strip()) < 40 * max(1, len(r.pages)):
            text += "\n[WARNING: little text extracted; the PDF may be scanned. Use pdftotext or OCR if available.]"
        return text
    except Exception as e:  # keep going: the workbook profile is still useful
        return f"[ERROR extracting PDF text: {e}]"


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def profile_sheet(ws_v, ws_f):
    cells = {}
    for row in ws_v.iter_rows():
        for c in row:
            if c.value is not None:
                cells[(c.row, c.column)] = c.value
    formulas = 0
    if ws_f is not None:
        for row in ws_f.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    formulas += 1
    from openpyxl.utils import get_column_letter as L
    out = {"dimensions": ws_v.dimensions, "non_empty_cells": len(cells), "formula_cells": formulas}
    if not cells:
        return out
    rows = {}
    for (r, c), v in cells.items():
        rows.setdefault(r, {})[c] = v
    # Text cells in the top rows / first column are titles and labels.
    labels = []
    for r in sorted(rows)[:400]:
        txt = [f"{L(c)}{r}={v!r}" for c, v in sorted(rows[r].items()) if isinstance(v, str)]
        if txt:
            labels.append(", ".join(txt)[:300])
    out["text_cells_sample"] = labels[:40]
    # Header row: the row with the most text cells immediately above a numeric run.
    numeric_rows = sorted(r for r, d in rows.items() if sum(is_num(v) for v in d.values()) >= 2)
    blocks = []
    for r in numeric_rows:
        if blocks and r - blocks[-1][1] <= 2:
            blocks[-1][1] = r
        else:
            blocks.append([r, r])
    block_info = []
    for a, b in blocks:
        counts = {}
        for r in range(a, b + 1):
            for c, v in rows.get(r, {}).items():
                if is_num(v):
                    counts[c] = counts.get(c, 0) + 1
        # Core columns hold numbers on most rows; sparse columns are displaced cells.
        cols = sorted(c for c, n in counts.items() if n >= 0.5 * (b - a + 1)) or sorted(counts)
        missing = [r for r in range(a, b + 1) if r not in rows]
        info = {"rows": f"{a}-{b}", "n_rows": b - a + 1,
                "numeric_cols": f"{L(cols[0])}:{L(cols[-1])}" if cols else "",
                "blank_rows_inside": missing[:20], "n_blank_rows_inside": len(missing)}
        hdr = rows.get(a - 1) or rows.get(a - 2) or {}
        info["header_above"] = {L(c): v for c, v in sorted(hdr.items())}
        info["first_rows"] = [{L(c): v for c, v in sorted(rows[r].items())} for r in range(a, min(a + 3, b + 1)) if r in rows]
        block_info.append(info)
    block_info.sort(key=lambda x: -x["n_rows"])
    out["numeric_blocks"] = block_info[:8]
    # Cells outside the main block's columns but inside its rows: displaced data.
    if block_info:
        main = block_info[0]
        a, b = map(int, main["rows"].split("-"))
        c0, c1 = main["numeric_cols"].split(":")
        from openpyxl.utils import column_index_from_string as CI
        c0, c1 = CI(c0), CI(c1)
        hdr_cols = {c for c in range(c0, c1 + 1)}
        stray = [f"{L(c)}{r}={v!r}" for (r, c), v in sorted(cells.items())
                 if a - 1 <= r <= b and c not in hdr_cols and not isinstance(v, str)]
        stray += [f"{L(c)}{r}={v!r}" for (r, c), v in sorted(cells.items())
                  if r > b and not isinstance(v, str)]
        out["numeric_cells_outside_main_block"] = stray[:60]
        textnum = [f"{L(c)}{r}={v!r}" for (r, c), v in sorted(cells.items())
                   if a <= r <= b and c0 <= c <= c1 and isinstance(v, str) and re.fullmatch(r"\s*-?\d+(\.\d+)?\s*", v)]
        out["numbers_stored_as_text"] = textnum[:30]
        if main["n_blank_rows_inside"] and stray:
            out["warning"] = (f"{main['n_blank_rows_inside']} blank row(s) inside the data block and numeric cells "
                              "outside it: records were likely moved out of the table. Recover them; do not drop them.")
    return out


def main():
    payload = json.load(sys.stdin)
    st = payload.get("currentState", payload)
    pdf = resolve(st.get("pdf_path"), "pdf_path")
    xlsx = resolve(st.get("xlsx_path"), "xlsx_path")
    from openpyxl import load_workbook
    try:
        wb_v = load_workbook(xlsx, data_only=True)
        wb_f = load_workbook(xlsx, data_only=False)
    except Exception as e:
        fail(f"cannot open workbook {xlsx}: {e}")
    prof = {"file": xlsx, "sheets": wb_v.sheetnames, "by_sheet": {}}
    for name in wb_v.sheetnames:
        prof["by_sheet"][name] = profile_sheet(wb_v[name], wb_f[name] if name in wb_f.sheetnames else None)
    print(json.dumps({"pdf_path": pdf, "xlsx_path": xlsx, "pdf_text": pdf_text(pdf),
                      "workbook_profile": prof}, default=str))


if __name__ == "__main__":
    main()
