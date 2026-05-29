# Financial Model Conventions

Load when the task asks for a financial model and the existing template does not already establish its own conventions. Existing template conventions ALWAYS override these guidelines.

## Color Coding (Industry Standard)

- **Blue text (RGB: 0,0,255)** — Hardcoded inputs; numbers users change for scenarios.
- **Black text (RGB: 0,0,0)** — ALL formulas and calculations.
- **Green text (RGB: 0,128,0)** — Links pulling from other worksheets within the same workbook.
- **Red text (RGB: 255,0,0)** — External links to other files.
- **Yellow background (RGB: 255,255,0)** — Key assumptions needing attention or cells that need to be updated.

## Number Formatting

- **Years** — Format as text strings (e.g., `"2024"` not `2,024`).
- **Currency** — Use `$#,##0` format; ALWAYS specify units in headers (e.g., `Revenue ($mm)`).
- **Zeros** — Use number formatting so all zeros render as `-`, including percentages, e.g. `"$#,##0;($#,##0);-"`.
- **Percentages** — Default to `0.0%` (one decimal).
- **Multiples** — Use `0.0x` for valuation multiples (EV/EBITDA, P/E).
- **Negative numbers** — Use parentheses `(123)` not minus `-123`.

## Formula Construction

### Assumptions Placement
- Place ALL assumptions (growth rates, margins, multiples) in separate assumption cells.
- Use cell references instead of hardcoded values in formulas.
- Example: `=B5*(1+$B$6)` instead of `=B5*1.05`.

### Documentation for Hardcodes
Comment the cell or use an adjacent cell (if end of table). Format:
`"Source: [System/Document], [Date], [Specific Reference], [URL if applicable]"`

Examples:
- `Source: Company 10-K, FY2024, Page 45, Revenue Note, [SEC EDGAR URL]`
- `Source: Company 10-Q, Q2 2025, Exhibit 99.1, [SEC EDGAR URL]`
- `Source: Bloomberg Terminal, 8/15/2025, AAPL US Equity`
- `Source: FactSet, 8/20/2025, Consensus Estimates Screen`
