---
name: powerlifting-scores-xlsx
description: Compute powerlifting scores (Dots, also Wilks and IPF GOODLIFT) for every lifter in an OpenPowerlifting/OpenIPF Excel workbook as live Excel formulas. Copies the needed columns (Name, Sex, BodyweightKg, Best3 lifts) to a score sheet, appends TotalKg and score formula columns with fixed-decimal rounding, recalculates with LibreOffice, and verifies every cell against the reference OpenPowerlifting implementation. Use for "calculate Dots/Wilks/GL coefficients in openipf.xlsx"-style tasks.
compatibility: python>=3.8 with openpyxl (3.1.5 tested); LibreOffice (`soffice`) for recalculation; gnumeric `ssconvert` optional fallback.
---

# Powerlifting scores in Excel

## Trigger When

1. A task asks for Dots (or Wilks / IPF GOODLIFT / Glossbrenner) points or coefficients for lifters in an `.xlsx` workbook.
2. The workbook holds OpenPowerlifting-style columns (`Name`, `Sex`, `BodyweightKg`, `Best3SquatKg`, `Best3BenchKg`, `Best3DeadliftKg`, …), often documented by `data-readme.md`.
3. The result must be Excel formulas (TotalKg, score) in a named sheet, with a fixed number of digits.
4. Comparing lifters across bodyweights or sexes from meet results in a spreadsheet.

## Purpose

Turns a sheet of meet results into a score sheet: picks exactly the columns the score needs, keeps their source order and header names, appends a `TotalKg` formula column and a score formula column, recalculates so cached values exist, then checks every value against the OpenPowerlifting formulas. It carries what an agent would otherwise get wrong: the exact Dots/Wilks/GL coefficients and bodyweight clamps, `Mx` scored as men, failed-lift and missing-bodyweight handling, and where rounding goes.

## Before the first script

Check that `python3 -c "import openpyxl"` works and `soffice --version` runs. Name anything that is missing. If openpyxl is missing, install it with `pip3 install --break-system-packages openpyxl` (or `uv pip install`). Run every command from the skill folder, or give scripts the full path. Pass the task's real workbook path. The scripts edit the workbook in place unless you pass `--output`.

## Procedure

Progress:
- [ ] 1. Read the task, the data readme, and answer `task_reading`
- [ ] 2. Build the sheet: `score_sheet.py build`
- [ ] 3. Recalculate: `recalc.py`
- [ ] 4. Verify: `score_sheet.py verify`
- [ ] 5. Report

### 1. Decision: `task_reading`

Input: the task statement. Answer all questions in one pass.

```yaml
score:
  type: choice
  instructions: Which points system does the task ask for?
  criteria:
    dots: Dots / DOTS / "Dynamic Objective Team Scoring".
    wilks: Wilks (the original Wilks formula, not Wilks2020).
    goodlift: IPF GL / IPF GOODLIFT / IPF points (2020 formula).
    other: Glossbrenner, Wilks2020, McCulloch, or anything else.
digits:
  type: choice
  instructions: How many decimal places does the task say to keep? "3 digits precision" means 3 decimal places. If the task does not say, use "3".
  criteria:
    "2": Two decimal places.
    "3": Three decimal places, or the task is silent.
    "4": Four decimal places.
    other: Another count (pass that integer to --digits).
round_coefficient:
  type: noul
  instructions: Does the task explicitly say to round the coefficient itself (500/polynomial) before multiplying it by the total?
  criteria:
    true: The text asks for the coefficient to be rounded on its own, or for a separate coefficient column that is rounded.
    false: The text only asks for overall precision ("keep 3 digits for all computation"). Rounding the TotalKg and the score is enough.
```

A false positive on `round_coefficient` moves scores by up to ~0.3 points, so reconsider any close call that leans yes. If `score` is `other`, read `references/coefficients.md`: Glossbrenner needs the Schwartz/Malone coefficients, which the sources do not include. Get those before writing formulas by hand with the same layout rules.

Also note the sheet names the task uses. The defaults are a source sheet named `Data` and an output sheet named after the score (`Dots`, `Wilks`, `Goodlift`). If the task uses other names, pass `--data-sheet` and `--out-sheet`.

### 2. Build

```bash
python3 scripts/score_sheet.py build /root/data/openipf.xlsx --score dots --digits 3
```
Add `--round-coefficient` if `round_coefficient` is true. Add `--data-sheet NAME` / `--out-sheet NAME` when the names differ.

What it does (deterministic):
- Finds columns by header name, not position. Copies `Name` plus the score's inputs, in their order in the data sheet, with the same header text, values, and number formats. Dots and Wilks need `Sex, BodyweightKg` plus the Best3 lifts. GOODLIFT also needs `Event, Equipment`. A source `TotalKg` column is never copied, because the task wants it computed by formula.
- Appends `TotalKg` = `=IF(MIN(lifts)<0,0,ROUND(SUM(lifts),d))`. A negative Best3 value is a failed lift, and per the readme a failed lift means no total.
- Appends the score column = `=IF(OR(bw="",bw<=0,TotalKg<=0),0,ROUND(TotalKg*coef,d))`. For Dots, coef = `IF(Sex="F", women, men)`: 500/poly4 with bodyweight clamped to [40,150] for women and [40,210] for men. `M` and `Mx` use the men's formula.
- Replaces an existing output sheet in the same tab position, so a pre-made empty "Dots" sheet is reused. The data sheet is left untouched.
- Prints JSON: `copied_columns`, the column letters, `dropped_source_TotalKg`, `failed_lift_cells_total_set_0`, and sample formulas. Read the sample formulas. If it exits 1, the message names the missing sheet or column and lists the headers that exist. Fix the arguments rather than editing the sheet by hand.

### 3. Recalculate

```bash
python3 scripts/recalc.py /root/data/openipf.xlsx 60
```
openpyxl writes formulas without values. Graders and readers that open the file with `data_only=True` see `None` until LibreOffice recalculates and saves. Expect `"status": "success"` and `total_errors: 0`. If it reports `errors_found`, see the error table in `references/xlsx-guidelines.md`, fix the cause, and rerun build and recalc. If it returns `{"error": ...}` (macro setup, first-start timeout), run it once more. If it fails again, fall back to `ssconvert --recalc in.xlsx out.xlsx`, then move `out.xlsx` over the original.

### 4. Verify

```bash
python3 scripts/score_sheet.py verify /root/data/openipf.xlsx --score dots --digits 3
```
Use the same flags as build. It checks the header order, that the copied values equal the data sheet, that TotalKg and the score are formulas, that every formula has a cached numeric value, and that each value matches an independent Python reference within 1.5×10⁻ᵈ. Exit 0 with `"status": "ok"` is required before you finish. On failure, the first 50 `problems` name the cell. "no cached value" means step 3 did not take effect.

### 5. Report (client task)

Write a short summary: the workbook path, the output sheet's columns in order, the row count, the formula used (paste one sample row), how failed lifts, missing bodyweight, and `Mx` were handled, and 2–3 example rows (name, TotalKg, score) from verify's `rows`.

## Gotchas

- Do not paste numbers computed in Python into the sheet. Every TotalKg and score must be an Excel formula, and the copied input columns are plain values.
- Keep the layout exact: copied columns first, in data-sheet order with identical names, then `TotalKg`, then the score column (`Dots`). Add no helper columns, constant cells, or extra sheets. That is why the coefficients sit inside the formula instead of in assumption cells.
- "3 digits precision" means `ROUND(...,3)` (3 decimals). Round the total and the final score, not the bodyweight inputs.
- The Dots polynomial is written high→low (A·x⁴ … E). The Wilks polynomial is written low→high (a + b·x …). Mixing them up gives coefficients that look plausible but are wrong.
- Never save a workbook that was opened with `data_only=True`, because that drops every formula.
- Another instance of the task may reorder columns, include a `TotalKg` column, contain bench-only rows (blank squat and deadlift), or have no empty output sheet. The script handles all of these by header lookup. Do not hardcode column letters.

## Resources

- `scripts/score_sheet.py`: build and verify (Dots, Wilks, GOODLIFT).
- `scripts/recalc.py`: LibreOffice recalculation and error scan, from the xlsx skill.
- `references/coefficients.md`: read when you need to hand-check a value, explain a coefficient, or handle Glossbrenner/other scores. It has all the coefficient tables, clamps, GL equipment mapping, and published test fixtures.
- `references/xlsx-guidelines.md`: read before making any spreadsheet change beyond what build does (extra formatting, summaries, manual edits) or when recalc reports errors.
