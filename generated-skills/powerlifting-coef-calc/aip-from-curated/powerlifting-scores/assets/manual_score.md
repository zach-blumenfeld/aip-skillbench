# Score system outside the pack

Task request:
{task_request}

Workbook profile:
{profile}

The request needs a scoring formula this pack does not script (supported: Dots, Wilks, IPF GL, Glossbrenner). Do it by hand with openpyxl, following `references/xlsx-rules.md`:
1. Get the formula, constants, bodyweight clamps and zero rules from the task text or an authoritative source you can cite. Do not guess coefficients; if you cannot obtain them, say so in the summary instead of inventing numbers.
2. Load the workbook with openpyxl (never with `data_only=True` if you will save), write the target sheet with live Excel formulas referencing the data sheet, and save.
3. If `soffice` is on PATH run `python scripts/recalc.py <file>` and fix every reported error until `status` is `success`; set `verify_status` to `pass`, or `pass_cached` if LibreOffice is unavailable, or `fail` if errors remain.
4. Spot-check 2-3 rows by computing them independently in Python.

Output `{{"output_path": "...", "verify_status": "pass|pass_cached|fail", "verification": {{"notes": "..."}}}}`.
