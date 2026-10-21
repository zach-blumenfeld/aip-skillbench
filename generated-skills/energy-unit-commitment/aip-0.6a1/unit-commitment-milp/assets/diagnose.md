The `{meta.name}` solve did not produce a schedule that passes independent validation, so no report was written.

Solver summary:
{solve_summary}

Validation result (failing checks and first violations):
{validation}

Parser issues recorded at load time:
{parse_issues}

The run used time_limit_s = {time_limit_s} and mip_rel_gap = {mip_rel_gap}.

Do this:
1. Classify the cause. No incumbent (status `no_incumbent`) or time limit hit: the fix is more solve time or a looser gap. Status `infeasible` or a failing check: follow "Debugging infeasibility" in the reference and inspect the input file for the parser issues listed above.
2. Fix it: for time, rerun this procedure from the start with a larger `time_limit_s` (e.g. double it) or a looser `mip_rel_gap` (0.005 to 0.01). For a model or data-mapping bug, correct `scripts/uc_core.py` (alias table or the named constraint family) and rerun.
3. Never write the report by hand and never set a constraint check to "pass" without a schedule that passed validation.

Answer with `failure_diagnosis`: the cause, the evidence from the summaries above, and the exact rerun or fix you applied or recommend.
