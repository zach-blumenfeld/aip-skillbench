# OpenIPF Data Sheet — Column Schema

The input workbook `/root/data/openipf.xlsx` has two sheets:

- **Data** — populated lifter records (one row per lifter-meet).
- **Dots** — empty; the skill fills this with formula-driven results.

The Data sheet follows the OpenPowerlifting CSV schema (see upstream
`data-readme.md`). Column letters below assume the standard OpenPowerlifting
column order; verify against the actual workbook headers before referencing
them in formulas.

## Columns needed for Dots

| Excel col | Header           | Why it's needed                          |
|-----------|------------------|------------------------------------------|
| A         | Name             | Lifter identity; copied to Dots sheet.   |
| B         | Sex              | Selects coefficient set (`M` vs `F`).    |
| I         | BodyweightKg     | Polynomial input; clamped per sex.       |
| K         | Best3SquatKg     | Summand for `TotalKg`.                   |
| L         | Best3BenchKg     | Summand for `TotalKg`.                   |
| M         | Best3DeadliftKg  | Summand for `TotalKg`.                   |

Columns **not** needed for Dots (Event, Equipment, Age, AgeClass,
BirthYearClass, Division, WeightClassKg, Place, Tested, Country, State,
Federation, ParentFederation, Date, MeetCountry, MeetState, MeetName,
Sanctioned, and any others) should **not** be copied to the Dots sheet.

## Dots sheet layout (target)

| Excel col | Header           | Source                                  |
|-----------|------------------|------------------------------------------|
| A         | Name             | `=Data!A{row}`                          |
| B         | Sex              | `=Data!B{row}`                          |
| C         | BodyweightKg     | `=Data!I{row}`                          |
| D         | Best3SquatKg     | `=Data!K{row}`                          |
| E         | Best3BenchKg     | `=Data!L{row}`                          |
| F         | Best3DeadliftKg  | `=Data!M{row}`                          |
| G         | TotalKg          | `=D{row}+E{row}+F{row}`                 |
| H         | Dots             | `ROUND(IF(...), 3)` (see dots-formula.md) |

Row 1 is the header row. Data rows start at row 2 and extend through
`data_row_count + 1`.

## Gotchas

- Header **order and names** must match the Data sheet for the six copied
  columns. Adding `TotalKg` and `Dots` is fine — those are new columns.
- The instruction file references column letters via the standard
  OpenPowerlifting ordering. If the cleaned workbook reorders columns,
  remap by **header name**, not by hard-coded letter — verify before writing
  formulas.
- `BodyweightKg`, `Best3SquatKg`, `Best3BenchKg`, `Best3DeadliftKg` are
  technically optional in the upstream schema. The cleaned task input has all
  four populated for every row; do not add defensive `IFERROR` wrapping.
- Three-digit precision applies to the final Dots score (via `ROUND(..., 3)`).
  `TotalKg` is an integer sum — no rounding needed.
