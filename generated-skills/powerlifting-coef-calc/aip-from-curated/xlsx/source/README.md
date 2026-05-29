# xlsx — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill `xlsx` (the `aip-from-curated`
track for the `powerlifting-coef-calc` task). The canonical original is
preserved verbatim at `source/ORIGINAL_SKILL.md`. The curated skill
shipped one executable, `recalc.py`, copied verbatim into `scripts/`.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md`.
- `source/procedure.schema.json` — the AIP `procedure` schema (v0.3a2)
  the body validates against. Bundled locally so the skill is
  self-contained.
- `scripts/recalc.py` — copied verbatim from the curated skill. Drives
  headless LibreOffice through a one-time Basic macro, recalculates every
  formula in every sheet, scans every cell for Excel error sentinels,
  and prints a JSON report.
- `scripts/financial_format.py` — new helper authored to encode the
  prose-only lookup tables from the original (color-coding palette,
  number-format dictionary, assumption-highlight fill). Per AIP best
  practice, lookup tables belong in `scripts/`, not in the body prose.

## Schema choice

`procedure` schema (reused, not drafted). The curated skill is an
execution graph: pick the library → load or create → write formulas →
apply formatting → save → recalculate → verify and fix. That maps
directly onto script-backed step nodes connected by inputs and outputs.
No new schema needed.

## Why `scripts/financial_format.py` was added

The curated `SKILL.md` defines its formatting conventions as prose:

- A color palette (blue inputs / black formulas / green cross-sheet /
  red external / yellow assumption highlight).
- A number-format dictionary (currency, percentages, multiples, years
  as text, parenthesised negatives, zero-suppression).

These are lookup tables and numeric conventions, exactly the kind of
content AIP routes through `scripts/`. Putting them in a Python module
gives the agent one place to import them, makes them queryable for
governance, and avoids drift between the body prose and the constants
the agent will type into openpyxl. The `apply-financial-formatting`
step is script-backed; the body just describes when to invoke it.

## Source-content classification (completeness check)

- "Zero Formula Errors" requirement → **Mapped** to `purpose`, the
  `recalculate-formulas` and `verify-and-fix-errors` steps, and an
  `anti_pattern`.
- "Preserve Existing Templates" rule → **Mapped** to
  `apply-financial-formatting` step description and an `anti_pattern`
  ("imposing the financial palette on an existing template").
- "Industry-Standard Color Conventions" table → **Mapped** to
  `scripts/financial_format.py::FINANCIAL_COLORS` +
  `ASSUMPTION_HIGHLIGHT_FILL`. Referenced by the
  `apply-financial-formatting` step.
- "Required Format Rules" (currency, percent, multiple, year, negatives,
  zero suppression) → **Mapped** to
  `scripts/financial_format.py::NUMBER_FORMATS`.
- "Assumptions Placement" rule (cell references over hardcoded
  constants) → **Mapped** to `write-formulas-not-values` step and
  `anti_patterns`.
- "Formula Error Prevention" checklist (off-by-one, circular references,
  edge cases) → **Mapped** to the `verify-and-fix-errors` step plus
  `anti_patterns`.
- "Documentation Requirements for Hardcodes" (source notation with
  date/page/URL) → **Mapped** to a `scenario` and an `anti_pattern`.
- "Reading and analyzing data with pandas" → **Mapped** to the
  `choose-library` step (pandas branch) and the `load-or-create-workbook`
  step.
- "CRITICAL: Use Formulas, Not Hardcoded Values" — both WRONG and CORRECT
  code examples → **Mapped** to `write-formulas-not-values` step plus an
  `anti_pattern`.
- "Common Workflow" enumeration (choose tool → load → modify → save →
  recalc → verify) → **Mapped**: it IS the step order.
- "Creating new Excel files" / "Editing existing Excel files" code
  snippets → **Mapped** to `load-or-create-workbook` step descriptions
  and `scenarios`.
- "Recalculating formulas" (`recalc.py` usage) → **Mapped** to
  `recalculate-formulas` step backed by `scripts/recalc.py`.
- "Formula Verification Checklist" (test 2–3 cells first, column
  mapping, row offset, NaN handling, far-right FY columns, multiple
  matches, division-by-zero, wrong refs, cross-sheet refs) → **Mapped**
  to step descriptions, `anti_patterns`, and a `scenario`.
- "Interpreting recalc.py Output" (JSON shape, error categories) →
  **Mapped** to the `recalculate-formulas` step's `recalc-report`
  output description and the `verify-and-fix-errors` description.
- "Best Practices — Library Selection" (pandas vs openpyxl) →
  **Mapped** to `choose-library` step.
- "Working with openpyxl" — 1-based indexing, `data_only=True` warning,
  `read_only=True` / `write_only=True` for large files → **Mapped** to
  `load-or-create-workbook` step plus an `anti_pattern` on the
  `data_only=True` save-loses-formulas trap.
- "Working with pandas" — `dtype`, `usecols`, `parse_dates` → **Mapped**
  to `load-or-create-workbook` step description.
- "Code Style Guidelines" (minimal Python, comments on complex formulas)
  → **Mapped** to a `scenario` and an `anti_pattern`.

## `do_not_use_when`

The original skill does not call out non-applicability. Two conditions
were added: non-Excel formats (Google Sheets API, native .ods — out of
scope) and pure-CSV transformations with no formulas (the recalc step
is wasted overhead). These keep the agent from over-applying the skill.

## `compatibility`

The original skill notes "LibreOffice Required for Formula
Recalculation" as a prerequisite. Promoted to the frontmatter
`compatibility` field so it surfaces before activation, not only inside
the body.
