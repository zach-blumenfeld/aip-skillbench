The score sheet `{score_sheet}` was written into `{workbook_path}` with live formulas, but the
post-write check did not pass. Status: `{recalc_status}`.

Check report (engine, formula errors, mismatches against an independent Python computation,
anomalies, backup path, sample rows):

{check_report}

Example formulas the script wrote in row 2:

{formula_examples}

Fix the workbook so every formula cell holds a correct cached value, without replacing formulas
with numbers:

- `not_recalculated`: no recalculation engine left cached values. Find LibreOffice (`soffice`,
  `libreoffice`, `/usr/lib/libreoffice/program/soffice`, `/Applications/LibreOffice.app/Contents/MacOS/soffice`)
  or gnumeric (`ssconvert`). Run `python scripts/recalc.py {workbook_path} 120` from the skill
  folder; if the macro fails, use `soffice --headless --convert-to xlsx --outdir <tmpdir> {workbook_path}`
  and copy the result back, or `ssconvert --recalc`. If no engine exists on this machine, say so
  plainly: the formulas are correct but values appear only when the file is opened in a
  spreadsheet application.
- `formula_errors`: open the listed cells, find the cause (text in a numeric column, a bad
  reference), correct the formula or the copied input, and recalculate.
- `mismatch`: a cached value disagrees with the expected value, or a total/score cell is not a
  formula. Compare the cell's formula with the example above and `references/scoring-formulas.md`;
  correct it and recalculate.

After fixing, re-run the check from the skill folder:
`python scripts/build_score_sheet.py --verify {workbook_path} --system {score_system} --decimals {decimals}`
and repeat until it reports `verified`. The original workbook is at the backup path if you need to
start over.

Answer with `fix_summary`: what was wrong, what you changed, and the final verify status.
