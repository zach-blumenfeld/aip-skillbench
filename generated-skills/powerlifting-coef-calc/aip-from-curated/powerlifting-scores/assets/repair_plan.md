# Repair the plan

`write_scores.py` reported `verify_status: fail`.

Task request:
{task_request}

Plan that failed:
{plan}

Verification report:
{verification}

Workbook profile:
{profile}

Fix the cause and emit a corrected `plan` (same schema). Typical causes:
- A header or sheet name in the plan does not exist in the workbook (check `profile.sheets[].headers`, exact case).
- Target sheet not empty: set `clear_target: true` only if the task wants it overwritten (a sheet this run already wrote is cleared automatically), otherwise pick the sheet the task names.
- A score column cannot find sex, bodyweight, or total: add the copy/total column or set its `inputs` mapping.
- `#NAME?`/`#VALUE!` from LibreOffice: a source column holds text where numbers are expected (see profile anomalies). Point the score at a numeric column, or tell the user that the data needs cleaning; never paste computed numbers over formulas to hide it.
- Mismatches against the Python reference with a clean recalc: report them in your final summary rather than looping; the reference implements the OpenPowerlifting formulas in `references/scoring-formulas.md`.

If the same error repeats after one repair, stop looping: keep the best plan and set `repair_action` to `stop`; the final check reports the unresolved problem.

Output: `{{"plan": {{...}}, "repair_action": "retry" | "stop"}}`.
