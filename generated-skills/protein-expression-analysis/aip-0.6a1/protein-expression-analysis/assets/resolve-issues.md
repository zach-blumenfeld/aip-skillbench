The filled workbook at {output_path} did not verify.

Issues:
{fill_issues}

Report:
{fill_report}

Fix each issue with the repair checklist in the reference: rerun the LibreOffice
recalculation (python scripts/recalc.py <file> 180 from the skill's scripts folder) if
it failed or timed out; correct a wrong or unresolved lookup by editing the formula or the
match, never by typing the number; restore the formulas-only copy if LibreOffice changed
fills or fonts visibly. Keep every target cell a formula, keep blanks for missing
measurements, do not touch non-target cells, and add no macros. Re-check that every yellow
cell holds a formula and no cell shows a # error. If something cannot be fixed (for
example LibreOffice is absent), leave the correct formulas in place and say exactly what
remains.
