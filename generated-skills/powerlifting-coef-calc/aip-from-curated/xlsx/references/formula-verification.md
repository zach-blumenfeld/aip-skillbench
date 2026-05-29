# Formula Verification Checklist

Load before declaring a workbook done. Walk every relevant item; do not skip.

## Essential verification

- [ ] **Test 2–3 sample references** — Verify they pull correct values before building the full model.
- [ ] **Column mapping** — Confirm Excel columns match (e.g., column 64 is `BL`, not `BK`).
- [ ] **Row offset** — Excel rows are 1-indexed (DataFrame row 5 = Excel row 6).

## Common pitfalls

- [ ] **NaN handling** — Check for null values with `pd.notna()`.
- [ ] **Far-right columns** — FY data often lives in columns 50+.
- [ ] **Multiple matches** — Search all occurrences, not just the first.
- [ ] **Division by zero** — Guard denominators before `/` (avoids `#DIV/0!`). E.g., wrap in `IFERROR(...)` or `IF(denom=0, "", num/denom)`.
- [ ] **Wrong references** — Verify every cell reference points where intended (avoids `#REF!`).
- [ ] **Cross-sheet references** — Use `Sheet1!A1` form for linking sheets.

## Formula testing strategy

- [ ] **Start small** — Test on 2–3 cells before applying broadly.
- [ ] **Verify dependencies** — Check that every referenced cell exists.
- [ ] **Test edge cases** — Include zero, negative, and very large values.
- [ ] **No circular references** — Verify no unintended cycles.
- [ ] **Consistent formulas across projection periods** — Same shape, just shifted references.

## Interpreting recalc.py output

The script returns JSON:

```json
{
  "status": "success",
  "total_errors": 0,
  "total_formulas": 42,
  "error_summary": {
    "#REF!": {
      "count": 2,
      "locations": ["Sheet1!B5", "Sheet1!C10"]
    }
  }
}
```

`status` is `success` or `errors_found`. If `errors_found`, fix the cells listed in `error_summary[*].locations` and recalculate.

Common error meanings:
- `#REF!` — Invalid cell reference (deleted, out of range).
- `#DIV/0!` — Division by zero.
- `#VALUE!` — Wrong data type in formula (e.g., text where number expected).
- `#NAME?` — Unrecognized formula or function name.
- `#N/A` — A lookup found nothing.
- `#NULL!` — Range intersection is empty.
- `#NUM!` — Numeric overflow or invalid argument.
