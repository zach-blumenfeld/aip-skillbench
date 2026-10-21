Review the final exam-sequencing outputs before handing them over.

Files written: {output_files}
Metrics recomputed from schedule.csv: {metrics}
Feasibility audit: {feasibility}
Overlap rule used: {overlap_rule}
Instance summary: {instance_summary}

Do this:

1. Open formulation.md and report.md. Confirm both quote the same objective as metrics.json, state
   "minimize", list each component with its start-slot mask, describe the overlap term with the rule
   above (not "all triples in four slots"), and report solver, time limit, status, incumbent, bound,
   and gap. If anything required by the task statement is missing, add prose to those two files.
   Never edit schedule.csv or metrics.json, and never change a number the scripts wrote; if a number
   looks wrong, say so in your summary instead.
2. Confirm the certificate wording: only "proven optimal" when the gap is closed; otherwise
   "feasible incumbent, not proven optimal".
3. If the task statement asks for an output file or field the scripts did not write, write it
   from the same final schedule and metrics.

Answer with `review_summary`: two to five sentences giving the final objective, its breakdown,
the feasibility result, the certificate (bound and gap), and any edits you made or concerns.
