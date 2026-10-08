# Final check

Task request:
{task_request}

Output workbook: {output_path}
Verify status: {verify_status}
Verification report:
{verification}

Before declaring the work done, confirm against the task text:
1. The target sheet and column headers match the task exactly (names, order, case); the data sheet is unchanged.
2. Every computed cell is a formula (copies too, unless the task asked for values) and `verification.errors` is empty: zero `#REF!`, `#DIV/0!`, `#VALUE!`, `#N/A`, `#NAME?`.
3. Rounding matches the request; `preview` and `score_ranges` look plausible (Dots/Wilks for competitive raw lifters typically fall around 200-600, IPF GL around 40-120; zeros only for failed totals or missing bodyweight).
4. `pass_cached` means LibreOffice was not available: formulas are intact and cached values come from the Python reference, which was cross-checked against the OpenPowerlifting test vectors. If `soffice` exists, run `python scripts/recalc.py <output_path>` yourself and confirm `status: success`.

Output `{{"summary": "<two to four sentences: file written, sheet and columns, score system and rounding, anomalies or caveats>"}}` plus keep `output_path` and `verify_status`.
