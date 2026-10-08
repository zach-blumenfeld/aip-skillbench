# Fix the inputs before solving

The network inspector found problems:

Issues: {issues}
Warnings: {warnings}
Network summary: {network_summary}
Counterfactual targets resolved so far: {counterfactual_targets}

Current inputs: network_path={network_path}, counterfactual={counterfactual}

Original request: {task_request}

Correct what you can and post `network_path`, `results_path`, and `counterfactual` for the solver:

- Wrong or missing file path: locate the network file the request names (check the task's working
  directory, e.g. `/root/`) and fix `network_path`.
- "no branch between buses F and T": re-read the request; check for swapped or mistyped bus numbers.
  Branch matching is already direction-insensitive, so only change the numbers if the request supports it.
- Malformed modification (missing `factor`/`limit_MW`, unknown `type`): rewrite it in the supported form.
- Infeasible data (capacity below load, reserves below requirement, unsupported cost model): do not
  alter the network; pass the inputs through unchanged so the solver reports the failure explicitly.

Never edit network.json itself.
