# Financial-model reading conventions

Use when the question hinges on interpreting the model's structure, assumptions, or
reported units — not when a cell value directly answers the question.

## Color coding (industry standard; may vary per model)
- **Blue text (RGB 0,0,255)**: hardcoded inputs — scenario knobs the modeler expects to change.
- **Black text (RGB 0,0,0)**: formulas and calculations.
- **Green text (RGB 0,128,0)**: links pulling from another sheet in the same workbook.
- **Red text (RGB 255,0,0)**: external links to another file.
- **Yellow fill (RGB 255,255,0)**: key assumption flagged for attention.

Font color lives at `cell.font.color.rgb` and fill at `cell.fill.start_color.rgb` in
openpyxl — read directly when you need to tell an input from a calculated value.

## Number formats and unit tells
- Years are often formatted as text (`"2024"` not `2024`); don't do arithmetic on them.
- Currency formats like `$#,##0;($#,##0);-` display negatives in parentheses and zeros as `-`.
- Column headers may encode units: `Revenue ($mm)`, `Margin (%)`. Preserve the unit in the answer; don't restate `$5,000` as `$5000mm`.
- `0.0%` means the stored value is a fraction (0.15 displays as 15.0%).
- `0.0x` means a valuation multiple (EV/EBITDA, P/E).

## Formula construction
- Assumptions sit in dedicated input cells; downstream formulas reference them (e.g. `=B5*(1+$B$6)`), not hardcoded growth rates. Trace input → calc → output along the formula chain.
- Consistent formulas across projection periods: a formula that differs mid-row is often a modeling bug or a scenario override.
- Watch for circular references and sign conventions (e.g. costs stored as positive but subtracted downstream).

## Source documentation
Hardcoded inputs are typically annotated with a source string in a comment or an
adjacent cell: `"Source: Company 10-K, FY2024, Page 45, Revenue Note, [SEC EDGAR URL]"`.
Surface the source when the answer leans on a hardcoded figure.

## Error values to flag
`#REF!`, `#DIV/0!`, `#VALUE!`, `#N/A`, `#NAME?` in a cached value mean the formula
broke — call this out and compute from upstream inputs when possible.
