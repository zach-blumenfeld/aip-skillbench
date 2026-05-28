# Financial model formatting standards

Apply these when authoring a financial model unless (a) the user specifies otherwise or (b) `study-existing-template` surfaced conventions in the existing file — in that case, **existing template conventions always override these defaults**.

## Color coding (text color)

| Cell content                                            | Color  | RGB           |
|---------------------------------------------------------|--------|---------------|
| Hardcoded inputs / scenario numbers the user will edit  | Blue   | 0, 0, 255     |
| Formulas and calculations                               | Black  | 0, 0, 0       |
| Links pulling from other worksheets in the same workbook| Green  | 0, 128, 0     |
| External links to other files                           | Red    | 255, 0, 0     |

| Cell role                                               | Background        | RGB           |
|---------------------------------------------------------|-------------------|---------------|
| Key assumptions needing attention / cells to update     | Yellow background | 255, 255, 0   |

## Number formatting

| Value type        | Format                          | Notes                                           |
|-------------------|---------------------------------|-------------------------------------------------|
| Years             | text string                     | `"2024"`, not `2,024`                           |
| Currency          | `$#,##0`                        | Specify units in headers, e.g. `Revenue ($mm)`. |
| Zeros             | render as `-`                   | Use `"$#,##0;($#,##0);-"` style for all numbers and percentages. |
| Percentages       | `0.0%`                          | One decimal by default                          |
| Multiples         | `0.0x`                          | EV/EBITDA, P/E, etc.                            |
| Negative numbers  | parentheses `(123)`             | Not `-123`                                      |

## Formula construction rules

### Assumptions placement
- Put every assumption (growth rate, margin, multiple, etc.) in a dedicated assumption cell.
- Reference assumption cells with `$`-anchored refs — `=B5*(1+$B$6)`, never `=B5*1.05`.

### Error prevention
- Verify cell references are correct.
- Check for off-by-one errors in ranges.
- Use consistent formulas across all projection periods.
- Test with edge cases: zero values, negatives, very large numbers.
- Avoid unintended circular references.

## Documentation for hardcoded values

Comment the cell, or place a note adjacent to the cell at the end of a table. Format:

```
Source: [System/Document], [Date], [Specific Reference], [URL if applicable]
```

Examples:
- `Source: Company 10-K, FY2024, Page 45, Revenue Note, [SEC EDGAR URL]`
- `Source: Company 10-Q, Q2 2025, Exhibit 99.1, [SEC EDGAR URL]`
- `Source: Bloomberg Terminal, 8/15/2025, AAPL US Equity`
- `Source: FactSet, 8/20/2025, Consensus Estimates Screen`
