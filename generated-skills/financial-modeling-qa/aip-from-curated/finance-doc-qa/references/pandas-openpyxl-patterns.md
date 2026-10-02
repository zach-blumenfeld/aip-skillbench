# pandas + openpyxl patterns for finance-doc QA

Load on demand when your analysis in `answer-question` needs recipes beyond the basics. Aimed at reading and analyzing existing `.xlsx` files (the task's `data.xlsx`); creating or editing spreadsheets is out of scope for this skill.

## Load the whole workbook, raw

Column locations, header rows, and merged cells are unreliable in unfamiliar workbooks. Read every sheet raw and coerce columns yourself:

```python
import pandas as pd

xls = pd.ExcelFile("/root/data.xlsx")
for name in xls.sheet_names:
    raw = pd.read_excel("/root/data.xlsx", sheet_name=name, header=None, dtype=object)
    print(name, raw.shape)
```

Coerce a column to integers robustly (strings, whitespace, and mixed types survive):

```python
def coerce_int_series(s: pd.Series) -> pd.Series:
    as_str = s.astype(str).str.strip()
    extracted = as_str.str.extract(r"(-?\d+)")[0]
    return pd.to_numeric(extracted, errors="coerce")

num = raw.apply(coerce_int_series)
```

## Detect columns by content, not by header

When headers are missing, wrong, or shifted, score each column by how well its values match the shape you expect. Example — find the six dice columns (values are integers in `[1..6]`) and the game-id column (each id appears exactly twice):

```python
def is_int_1_6(x): return pd.notna(x) and (x % 1 == 0) and 1 <= x <= 6

col_scores = []
for c in num.columns:
    vals = num[c].dropna()
    if len(vals) < 50:
        continue
    frac = ((vals >= 1) & (vals <= 6) & ((vals % 1) == 0)).mean()
    col_scores.append((float(frac), int(len(vals)), c))
col_scores.sort(reverse=True)
dice_idx = sorted(t[2] for t in col_scores[:6])

def game_like_score(col_idx):
    s = num[col_idx].dropna()
    if len(s) < 200:
        return -1
    s = s[(s % 1) == 0].astype(int)
    vc = s.value_counts()
    frac_twice = (vc == 2).mean() if len(vc) else 0
    frac_once  = (vc == 1).mean() if len(vc) else 0
    sc = 0.0
    sc += 1.0 if int(s.min()) == 1 else 0.0
    sc += 4.0 * frac_twice
    sc -= 1.5 * frac_once
    return sc

game_col = max((c for c in num.columns if c not in dice_idx), key=game_like_score)
```

The same idea generalizes: identifiers appear as small-integer sequences; categorical columns have few unique values; date columns parse cleanly with `pd.to_datetime(..., errors="coerce")`.

## Group and aggregate deterministically

```python
sub = num[[game_col] + dice_idx].copy()
sub.columns = ["game", "r1", "r2", "r3", "r4", "r5", "r6"]
sub = sub.dropna(subset=["game", "r1", "r2", "r3", "r4", "r5", "r6"])
sub["game"] = sub["game"].astype(int)

for gid, gdf in sub.groupby("game", sort=True):
    gdf = gdf.sort_index()  # or sort_values("turn") if you detected a turn col
    ...
```

## Handle "known-good" rows the source PDF mentions

If the background PDF lists an example row or a correction that should be present, ensure it before scoring:

```python
missing = {"game": 8, "r1": 4, "r2": 6, "r3": 4, "r4": 2, "r5": 4, "r6": 5}
mask = (sub["game"] == missing["game"])
for c in ["r1", "r2", "r3", "r4", "r5", "r6"]:
    mask &= (sub[c] == missing[c])
if not mask.any():
    sub = pd.concat([sub, pd.DataFrame([missing])], ignore_index=True)
```

## openpyxl — when you need formulas or formatting

```python
from openpyxl import load_workbook
wb = load_workbook("/root/data.xlsx", data_only=True)  # read computed values
for name in wb.sheetnames:
    ws = wb[name]
    print(name, ws.max_row, ws.max_column)
```

`data_only=True` returns the cached calculated value. If a formula has never been computed (opened only in openpyxl), the cell is `None`; you'll then have to recompute in Python or in Excel/LibreOffice yourself.

## When you know the shape ahead of time

Skip the raw-load-and-coerce when the workbook has a clean header row you trust:

```python
df = pd.read_excel("/root/data.xlsx", sheet_name="Sheet1",
                   usecols=["id", "revenue", "date"],
                   dtype={"id": str},
                   parse_dates=["date"])
```

- `usecols=` — narrow to the columns you actually need on very wide workbooks.
- `dtype={"id": str}` — force string typing on identifier-like columns that would otherwise be coerced to `int` or `float` and lose leading zeros.
- `parse_dates=` — parse date columns at read time; avoids per-row `pd.to_datetime` later.

## Common pitfalls

- Excel rows are 1-indexed; pandas is 0-indexed. Excel column 64 is `BL`, not `BK`.
- `NaN` is not equal to `NaN`. Filter with `.notna()` / `.isna()`, not `== NaN`.
- Header cells often bleed into data (a title row, then a blank, then the real header). Prefer `header=None` and detect the header row yourself.
- Merged cells appear as the value in the top-left cell and `None` elsewhere. Forward-fill columns whose category labels come from merged headers: `raw[c] = raw[c].ffill()`.
- Sheet name lookups are case-sensitive. Use `xls.sheet_names` verbatim.
- Very wide workbooks may put the answer data in columns 50+; scan all columns, not just the first few.
