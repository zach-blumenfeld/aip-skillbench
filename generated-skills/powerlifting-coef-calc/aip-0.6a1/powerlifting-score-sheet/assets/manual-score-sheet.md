The task asks for a powerlifting score that `scripts/build_score_sheet.py` does not build
(it covers Dots, Wilks and IPF GL only). Build the score sheet in `{workbook_path}` by hand.

Task statement:

{task_statement}

Round every computed value to {decimals} decimals with Excel `ROUND`.

1. Load `references/scoring-formulas.md` and find the requested formula, its parameters, clamps,
   sex mapping (M and Mx use men's values) and zero rules. If the source material lacks a needed
   constant (for example the Schwartz/Malone coefficients behind Glossbrenner), say exactly what
   is missing instead of inventing numbers.
2. With openpyxl, find the data sheet and copy only the columns the formula needs, plus `Name`,
   into the target sheet named by the task, keeping the data sheet's column names and order.
   Never copy an existing `TotalKg`; recompute it.
3. Append `TotalKg` as `=ROUND(SUM(<squat>,<bench>,<deadlift>),{decimals})`, then the score column
   as an Excel formula over that row's cells. Guard blank or zero bodyweight and zero total with
   `N()` so they score 0 instead of erroring. No values computed in Python.
4. Save, recalculate (`python scripts/recalc.py {workbook_path} 120`, from the skill folder), and
   confirm zero formula errors. Spot-check two rows against a hand computation.

Answer with `manual_summary`: the sheet and columns written, the formula used, the recalc result,
and anything you could not do.
