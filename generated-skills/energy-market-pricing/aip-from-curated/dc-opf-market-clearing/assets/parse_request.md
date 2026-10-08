# Parse the market-analysis request

Request (verbatim):

{task_request}

Turn it into the structured inputs for `{meta.name}`. Produce JSON with exactly these keys:

- `network_path` (string): absolute path of the MATPOWER-style network JSON the request names
  (e.g. `/root/network.json` in the task container). Do not open or print the file here; the next
  step inspects it with a parser.
- `output_path` (string): where the request wants the final report written (e.g. `/root/report.json`).
  If none is named, use `report.json` next to the network file. Resolve a relative path against the
  directory the task is run from (the task's working directory, e.g. `/root/` in the container).
- `results_path` (string): scratch file for full solver results, in a writable work directory that is
  NOT the output path (e.g. `/root/dcopf_results.json` or `/tmp/dcopf/results.json`).
- `counterfactual` (object): `{{"enabled": false}}` when only a base case is asked for, otherwise
  `{{"enabled": true, "modifications": [ ... ]}}` with one entry per change the request describes:
    - `{{"type": "line_limit", "from_bus": F, "to_bus": T, "factor": 1.2}}` for "increase the limit of
      line F-T by 20%"; use `"limit_MW": X` instead of `factor` for an absolute new rating. Bus pairs
      are direction-insensitive. Add `"match": "all"` only if the request says every parallel circuit
      between the two buses changes (default `"first"` = the first branch row listed for that pair,
      which is what the reference method does).
    - `{{"type": "bus_load", "bus": B, "factor": x | "delta_MW": d | "pd_MW": p}}` for load changes.
    - `{{"type": "reserve_requirement", "factor": x | "value_MW": v}}` for reserve-requirement changes.
- `report_requirements` (string): the request's required output schema AND every quantity or question
  it asks to report (e.g. "top 5 buses by absolute price change", "load-weighted average LMP"), with
  wording about units, rounding, sorting, or top-N lists, copied as exactly as possible. Write
  "none specified" only if the request asks for nothing beyond the default market results.

Percentages mean multiplicative factors (20% increase -> factor 1.2; 10% decrease -> 0.9).
