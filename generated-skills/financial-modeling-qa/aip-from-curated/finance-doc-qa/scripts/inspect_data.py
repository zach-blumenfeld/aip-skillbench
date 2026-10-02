#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def _column_profile(df, c):
    s = df[c]
    non_null = s.dropna()
    n_non_null = int(non_null.shape[0])
    sample = [str(v) for v in non_null.head(5).tolist()]
    prof = {"n_non_null": n_non_null, "sample_non_null": sample}
    try:
        import pandas as pd
        num = pd.to_numeric(non_null, errors="coerce").dropna()
        if len(num) >= max(10, int(0.1 * n_non_null)):
            prof["numeric_share"] = round(float(len(num) / max(1, n_non_null)), 3)
            prof["numeric_min"] = float(num.min())
            prof["numeric_max"] = float(num.max())
            prof["numeric_n_unique"] = int(num.nunique())
    except Exception:
        pass
    return prof


def _describe_sheet(name, df):
    import pandas as pd

    rows, cols = df.shape
    non_empty_mask = df.notna().any(axis=1)
    first_non_empty = int(non_empty_mask.idxmax()) if non_empty_mask.any() else 0
    preview_rows = []
    seen = 0
    for idx in df.index[first_non_empty:]:
        row = df.loc[idx].tolist()
        if any(pd.notna(v) for v in row):
            preview_rows.append({"excel_row": int(idx) + 1, "cells": [str(v) if pd.notna(v) else None for v in row]})
            seen += 1
            if seen >= 15:
                break

    per_column = {str(c): _column_profile(df, c) for c in df.columns}

    return {
        "sheet": name,
        "rows": int(rows),
        "cols": int(cols),
        "first_non_empty_row_excel_1_indexed": first_non_empty + 1,
        "preview_non_empty_rows": preview_rows,
        "per_column": per_column,
    }


def main() -> None:
    payload = json.load(sys.stdin)
    state = payload.get("currentState", {})
    path = Path(state["data_path"])
    if not path.exists():
        raise FileNotFoundError(f"data_path not found: {path}")

    import pandas as pd

    xls = pd.ExcelFile(path)
    sheet_names = list(xls.sheet_names)

    summaries = []
    for name in sheet_names:
        raw = pd.read_excel(path, sheet_name=name, header=None, dtype=object)
        summaries.append(_describe_sheet(name, raw))

    data_summary = {
        "path": str(path),
        "sheet_names": sheet_names,
        "sheets": summaries,
    }

    json.dump({"data_summary": json.dumps(data_summary, default=str)}, sys.stdout)


if __name__ == "__main__":
    main()
