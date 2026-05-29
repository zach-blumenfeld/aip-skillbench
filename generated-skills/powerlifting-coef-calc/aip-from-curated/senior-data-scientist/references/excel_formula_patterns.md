# Excel Formula Construction Patterns (xlsxwriter)

Recipes used by `scripts/build_dots_workbook.py`. Stay with xlsxwriter for
write paths and openpyxl for read-back verification — that combination
preserves formula strings without quoting drift across Excel versions.

## Cross-sheet cell reference

```python
worksheet.write_formula(row_0idx, col_0idx, f"=Data!{src_letter}{excel_row}")
```

Both row indices and column indices in `write_formula` are 0-based. The Excel
cell address inside the formula string is 1-based. Mixing them is the most
common bug; convert at the boundary.

## Column-letter helper

xlsxwriter does not expose a 1-based-index → letter helper. Roll a tiny one:

```python
from string import ascii_uppercase

def col_letter(idx_1: int) -> str:
    n, out = idx_1, ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out = ascii_uppercase[rem] + out
    return out
```

Handles AA, AB, …, ZZ; the OpenIPF Data sheet usually fits in A..Z.

## Sex-switched arithmetic

```python
formula = f'=IF({sex_cell}="M",{male_expr},{female_expr})'
```

Quoting note: write the comparison value as `"M"` (double-quotes inside the
f-string) — xlsxwriter passes the string straight through.

## Clamped bodyweight subexpression

```python
def clamp(bw_cell, lo, hi):
    return f"MAX({lo},MIN({hi},{bw_cell}))"
```

Inline this expression at every `POWER(...)` reference so the clamp is applied
identically everywhere. Do not assign it to a helper Excel cell — that
introduces an order-of-evaluation dependency that breaks on row insertion.

## ROUND wrapping

```python
formula = f"=ROUND({inner},3)"
```

`ROUND` wraps the *outer* expression once. Rounding inner polynomial terms
loses precision before the division by 500/poly.

## TotalKg as sum, not as named range

```python
worksheet.write_formula(row_0idx, 6, f"=D{excel_row}+E{excel_row}+F{excel_row}")
```

Three explicit references beat `SUM(D{r}:F{r})` because the explicit form
makes the per-cell precedents visible in Excel's audit tool and is what the
verifier checks for.

## PEP 723 inline metadata for `uv run`

All scripts in this skill carry an inline metadata header so `uv run` resolves
dependencies on first invocation without a project file:

```python
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "polars==1.37.1",
#   "fastexcel==0.18.0",
#   "xlsxwriter==3.2.9",
# ]
# ///
```

Pinning versions matches the OpenPowerlifting reference solution and keeps
formula-string output byte-stable across reruns.

## Reading back to verify (openpyxl)

```python
import openpyxl
wb = openpyxl.load_workbook(path, data_only=False)   # keep formula strings
ws = wb["Dots"]
assert isinstance(ws["H2"].value, str) and ws["H2"].value.startswith("=")
```

`data_only=True` would replace the formula string with the cached numeric
result — useless for verifying that formulas were actually written.

## Anti-patterns

- Using `xl_rowcol_to_cell` from `xlsxwriter.utility` for the cross-sheet
  reference inside a formula string. It works but obscures the row/col
  indexing convention. Inline the letter helper instead.
- Writing the TotalKg sum as `SUM(D{r}:F{r})`. Verifier checks for explicit
  `D{r}`, `E{r}`, `F{r}` substrings.
- Mixing `worksheet.write` and `worksheet.write_formula`. Use `write_formula`
  for every computed cell so Excel recomputes on open.
