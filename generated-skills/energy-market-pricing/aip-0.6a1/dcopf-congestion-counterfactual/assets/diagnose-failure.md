Market clearing for the "what if we relax line {line_from_bus}-{line_to_bus} by
{capacity_increase_pct}%" analysis on `{network_path}` did not finish.

Reason reported by the solver script:

{status_detail}

Diagnose it from the network file. Load `references/market-model.md` (section "Failure
causes"); load the file with `json.load` (never page it with sed/head). Check the
specific cause: whether the line exists (either orientation, BR_STATUS = 1); the load
balance against online PMAX; reserve requirement vs capacity; islands; any malformed
gencost rows. Do not invent prices or write a report.json from guesses: a report needs
both market clearings to solve.

Answer with:
- `failure_diagnosis`: the root cause in one or two sentences, citing the numbers you
  checked.
- `corrected_inputs`: an object with corrected start inputs (`network_path`,
  `line_from_bus`, `line_to_bus`, `capacity_increase_pct`, `report_path`) if the
  cause is a wrong input that the evidence clearly resolves (e.g. the only line between
  those buses is listed under different numbers in the task statement). Otherwise use
  an empty object. Rerun the procedure with them yourself.
