# OpenPowerlifting / OpenIPF Data Sheet — Column Dictionary

The OpenPowerlifting "Data" sheet uses the columns documented at
<https://gitlab.com/openpowerlifting/opl-data/blob/main/docs/data-readme.md>.
Only the columns needed by this skill are summarised here; consult the
upstream README for the full schema.

## Required for Dots

| Header              | Mandatory? | Semantics                                                                                  |
|---------------------|------------|--------------------------------------------------------------------------------------------|
| `Name`              | Yes        | UTF-8 lifter name. Duplicates are disambiguated with `#1`, `#2` suffixes.                  |
| `Sex`               | Yes        | `M`, `F`, or `Mx`. The Dots polynomial is defined only for `M` and `F`.                    |
| `BodyweightKg`      | No         | Bodyweight at competition, two decimal places. Required as the polynomial input.           |
| `Best3SquatKg`      | No         | Max of the first three successful squat attempts. Rarely negative for failed-only entries. |
| `Best3BenchKg`      | No         | Max of the first three successful bench attempts.                                          |
| `Best3DeadliftKg`   | No         | Max of the first three successful deadlift attempts.                                       |

`TotalKg` already exists in the Data sheet but **is not copied** — the Dots
sheet recomputes it via formula from the three Best3 columns. This matches the
task instruction's "use Excel formula to compute each lifter's total" wording.

## Important context (not copied, but relevant)

| Header        | Use                                                                                |
|---------------|------------------------------------------------------------------------------------|
| `Event`       | `SBD` (Squat-Bench-Deadlift) is the only event where all three Best3 fields apply. |
| `Equipment`   | `Raw`, `Wraps`, `Single-ply`, `Multi-ply`, `Unlimited`, `Straps`. Dots ignores it. |
| `Place`       | `DQ`, `DD`, `NS`, or numeric placing. `TotalKg` may be empty for non-finishers.    |

## Handling edge cases in the Excel output

- **Empty `BodyweightKg`** — `POWER(0,…)` evaluates to 0 inside the polynomial
  and produces `#DIV/0!` once divided. This is the correct behaviour for
  missing data; do not pre-filter rows.
- **Empty `Best3*Kg`** — the `=D+E+F` TotalKg formula sums blanks as 0 and
  produces 0 for the Dots column. Some upstream pipelines drop such rows; do
  not silently drop them here — leave them so verification of row count
  matches the source.
- **`Mx` sex** — falls through to the female polynomial branch. Surface this
  to the user if the input has any `Mx` rows.
- **Negative `Best3*Kg`** — some federations encode failed-only entries as
  negatives. Dots scores on those will be nonsense. Flag them but leave them
  in place unless the user asks to drop them.

## Column-letter mapping in the canonical OpenIPF workbook

These positions are typical, but the skill resolves them dynamically from the
header row — never hard-code them in scripts.

| Header              | Typical letter |
|---------------------|----------------|
| `Name`              | A              |
| `Sex`               | B              |
| `BodyweightKg`      | I              |
| `Best3SquatKg`      | K              |
| `Best3BenchKg`      | L              |
| `Best3DeadliftKg`   | M              |
