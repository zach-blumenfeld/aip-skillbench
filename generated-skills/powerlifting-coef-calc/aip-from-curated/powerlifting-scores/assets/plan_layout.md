# Plan the scoring sheet

Task request:
{task_request}

Score system chosen: {score_system}

Workbook profile (from profile_workbook.py):
{profile}

Draft plan (header-matched guess, edit it to fit the task exactly; its target sheet and score header are guessed from empty sheet names, e.g. an empty `Dots` sheet, so replace them when the task names another sheet or system):
{draft_plan}

Produce `plan`, a JSON object that `scripts/write_scores.py` executes. Fields:

| field | meaning |
|---|---|
| `output_path` | Absolute path to write. Default: the input workbook, edited in place. Use another path only when the task names one. |
| `data_sheet` | Sheet holding the lifter rows (header in row 1, data from row 2). |
| `target_sheet` | Sheet to fill (created if missing). Use the exact name the task gives (e.g. an existing empty `Dots` sheet). |
| `clear_target` | `true` only if the target already has content the task wants replaced. |
| `copy_mode` | `formula` (default: `=Data!A2` references, so the sheet stays live) or `value` (only if the task asks for static copies). |
| `failed_lift_policy` | `opl` (default): total = 0 when any listed lift is negative (negative = failed attempt, OpenPowerlifting leaves TotalKg empty). `sum`: plain SUM of the cells. |
| `columns` | Ordered list; column A first. Each item has `header` plus one of the kinds below. |
| `sort_by` | Optional `{{"header": "<target column>", "descending": true}}` when the task asks to rank/order lifters. Rows are ordered once at write time (ties keep Data order); the formulas stay live but the row order does not re-sort if Data changes. |
| `freeze_header` | Optional `true` to freeze row 1. |
| `recalc_timeout` | Optional LibreOffice timeout in seconds (default 60). |

Column kinds:
- `{{"header": "Name", "kind": "copy", "source": "Name"}}`: copy a Data column by header.
- `{{"header": "TotalKg", "kind": "total", "sources": ["Best3SquatKg", "Best3BenchKg", "Best3DeadliftKg"], "round": null}}`: sum of lifts. Sources resolve to copied target columns first, else Data columns.
- `{{"header": "Rank", "kind": "rank", "of": "GL Points", "ascending": false}}`: Excel `RANK` of another target column (1 = highest; ties share a rank). Add it only when the task asks for a rank/place column.
- `{{"header": "Dots", "kind": "score", "system": "dots", "round": 3}}`: one of `dots`, `wilks`, `ipf_gl`, `glossbrenner`; each score column's `system` wins over the routed `score_system` (with `multiple`, set it on every score column). Optional `"output": "coefficient"` writes the bare coefficient (points per kg of total, i.e. the score with total = 1) instead of points; use it only when the task asks for the coefficient itself rather than the score. "Calculate the Dots coefficients" next to a requested TotalKg column and a column named `Dots` means the Dots score (points, as in OpenPowerlifting's Dots column); write the bare multiplier only when the task defines it without the total or asks for both (then add two score columns). Optional `inputs` maps `sex`, `bodyweight`, `total`, `equipment`, `event` to a header when auto-matching would pick the wrong column. Optional `number_format`.

Rules:
1. Follow the task text literally: sheet names, column headers (exact spelling and case), column order, which columns to copy, rounding digits. When the task lists the columns, write exactly those (a total or score can read lifts straight from Data without copying them). Only when the task gives no column list, keep the draft's defaults: Name, Sex, BodyweightKg, the Best3 lifts, then TotalKg, then the score.
2. A total sums whichever lift cells exist: bench-only (B) or deadlift-only (D) entries total just that lift, matching OpenPowerlifting. A blank source cell copied by formula shows as 0 (Excel semantics) and a 0 bodyweight scores 0.
3. If Data already has a `TotalKg` column, copy it instead of recomputing, unless the task says to compute the total. A blank OPL TotalKg means a failed or disqualified lifter and yields 0 points.
4. `round` wraps the cell in Excel `ROUND(...,n)`. Set it only when the task asks for rounding or a fixed number of decimals; otherwise `null` (keep full precision, display formatting is separate).
5. IPF GL needs Equipment and Event: it is defined only for `SBD` and `B` events (others score 0). Keep them reachable (copied or in Data).
6. Do not add extra columns, notes, coefficient tables, or colour coding to the target sheet unless the task asks; graders and users read the layout as given.
7. Every formula takes kilograms. If the workbook's bodyweight or lifts are in pounds (headers like `BodyweightLbs`, values ~2.2x kg), stop and convert first (1 lb = 0.45359237 kg) with a kg helper column the task allows, or report it; never feed pounds to the scripts.
8. Use the anomalies list: negative lifts, blank bodyweights, DQ places, and non-M/F sexes change totals or points. Pick `failed_lift_policy` with them in mind.

Output: `{{"plan": {{...}}}}`.
