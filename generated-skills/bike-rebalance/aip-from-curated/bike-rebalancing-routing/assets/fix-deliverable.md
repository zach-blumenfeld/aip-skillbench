# Fix the deliverable

The independent validator rejected `{output_path}`:

{issues}

Recomputed from the raw data: {recomputed}

Decide which side is wrong and fix it:

- **Transcription / format drift** (renamed key lost a quantity, internal index written instead of a
  station ID, totals copied from the wrong field, rounding inside totals, missing vehicle, missing
  depot label): regenerate `{output_path}` programmatically from `{solution_path}`.
- **Validator blind spot** (the task's schema names a field the validator does not recognise, e.g.
  quantities under an unusual key, or the task itself prescribes the flagged form): add the canonical
  keys alongside the task's keys only if the task schema tolerates extra keys; otherwise verify that
  issue by hand and return it in `waived_issues` (a distinctive substring of the issue text) with
  `waiver_reason`. Never waive a capacity, inventory, ID, or distance violation that is real.
- **Model-level violation** (load over capacity, station inventory breached, split service when
  forbidden, deviation from the solver's own objective): the assumptions passed to `solve` disagree
  with the report or the task. Re-check `task_text` against `vehicles_must_be_used`,
  `split_service_allowed`, `end_empty_required`, `penalty_form`, `initial_vehicle_load`; correct the
  state and re-run the solver — `scripts/solve_rebalancing.py`, or the adapted copy if
  `custom_objective` is set — with the same stdin contract (`{{"currentState": <state>}}`), then
  rewrite the report.

Never edit numbers by hand to make the check pass. Return JSON: `{{"data_path": ..., "output_path": "<absolute path>", "solution_path": ...}}` (unchanged unless you re-solved), plus `waived_issues` / `waiver_reason` only if used.
