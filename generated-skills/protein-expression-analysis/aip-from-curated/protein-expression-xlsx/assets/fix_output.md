# Repair the output workbook

Verification did not pass. Status: {verify_status}

Output workbook: {output_path}
Report:
{verify_report}

Build notes: {build_notes}

Fix by cause:
- `recalc_unavailable` / `recalc_failed`: the formulas exist but have no cached values, so anything reading the file with openpyxl `data_only=True` sees empty cells. First check `which soffice` (recalc.py raises FileNotFoundError without it). Get LibreOffice to recalculate: run `python3 scripts/recalc.py <output_path> 90` from the skill folder and read its JSON. If it reports a macro error, run `soffice --headless --terminate_after_init` once to create the profile and retry. Fallback: `soffice --headless --calc --convert-to xlsx --outdir <tmpdir> <output_path>` and copy the converted file over the output. Gnumeric is installed in the task container (check `which ssconvert` elsewhere): `ssconvert --recalc <in.xlsx> <out.xlsx>` recalculates, but check fills and formulas survive before keeping its output. If none of these can run here (no LibreOffice on this machine), report `unresolved`.
- `errors_found`: a formula returns #DIV/0!, #N/A, #NAME?, #REF! or #VALUE!. Read the listed cells. #NAME? usually means a modern function name written without its `_xlfn.` prefix (use STDEV/STDEVP, not STDEV.S/STDEV.P). #DIV/0! means a group has too few values: the stats formulas must keep their COUNT guard. #N/A means a Protein_ID or sample name did not MATCH: compare spelling, whitespace and isoform suffixes (`-2`) with the data sheet.
- `mismatch`: cached values differ from the Python shadow values, or formulas were lost. A cell mapped to the wrong protein or sample means the layout is wrong: correct `layout` and re-run `scripts/build_formulas.py` (stdin `currentState` = the current state) so `expected` is regenerated, then let `verify` run again. Never save a workbook loaded with `data_only=True`; that strips every formula.

Read `references/xlsx-guide.md` for the general formula rules and the recalc.py output format.

Return `fix_outcome`: `refixed` when you changed something and verification should run again; `unresolved` when the problem cannot be fixed in this environment. Also return `fix_notes` (string) saying what you did or why it is unresolved, and the regenerated `expected` if you re-ran build.
