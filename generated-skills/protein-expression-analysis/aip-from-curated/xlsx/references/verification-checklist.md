# Verification checklist

Run before delivering any spreadsheet.

## Essential

- [ ] **Test 2–3 sample references first** before building the full model — verify they pull the right values.
- [ ] **Column mapping** — confirm Excel columns match (column 64 = BL, not BK).
- [ ] **Row offset** — Excel rows are 1-indexed (DataFrame row 5 = Excel row 6).

## Common pitfalls

- [ ] **NaN handling** — check with `pd.notna()` before writing.
- [ ] **Far-right columns** — FY data often sits in columns 50+.
- [ ] **Multiple matches** — search all occurrences, not just the first.
- [ ] **Division by zero** — guard denominators (`=IFERROR(... , "")`) to avoid `#DIV/0!`.
- [ ] **Wrong references** — verify each ref points to the intended cell (`#REF!`).
- [ ] **Cross-sheet references** — use `Sheet1!A1` form.

## Formula testing strategy

- [ ] Start small — test on 2–3 cells before applying broadly.
- [ ] Verify every referenced cell exists.
- [ ] Test edge cases: zero, negative, very large.

## Interpreting recalc.py output

`scripts/recalc.py` writes JSON like:

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

When `status` is `errors_found`, each `error_summary` key names an Excel error type with locations to inspect.

| Error      | Typical cause                                              | Fix                                                |
|------------|------------------------------------------------------------|----------------------------------------------------|
| `#REF!`    | Reference to a deleted/invalid cell                        | Correct the reference                              |
| `#DIV/0!`  | Division by zero                                           | Guard with `IF`/`IFERROR`; check denominator        |
| `#VALUE!`  | Wrong data type in formula (e.g., text passed to math)     | Align types; coerce or replace inputs              |
| `#NAME?`   | Unrecognized function name or named range                  | Fix spelling, check workbook locale                |
| `#NULL!`   | Range intersection that doesn't exist                      | Use comma `,` or colon `:` instead of space        |
| `#NUM!`    | Numeric overflow or invalid math argument                  | Bound inputs; verify domain                        |
| `#N/A`     | Lookup miss                                                | Add `IFERROR` or check the lookup table            |

After fixes, save and re-run recalc until `status` is `"success"`.

## Final delivery gate

- [ ] `recalc.py` reports `status: "success"` with `total_errors: 0`.
- [ ] Hardcoded values have a source comment or adjacent note in the documented format.
- [ ] Color and number formatting match either the existing template conventions or the financial-model defaults.
- [ ] Every formula cell shows a computed value (no blanks after recalc).
