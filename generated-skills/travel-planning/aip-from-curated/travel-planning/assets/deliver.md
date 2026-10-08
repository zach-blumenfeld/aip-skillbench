# Deliver the plan

Request:

{request}

Validation: {validation_outcome} after {validation_attempts} attempt(s). Total cost {total_cost} against budget {budget}. Remaining violations: {violations}. Warnings: {warnings}.

Final plan:

{plan}

Deliver it in the form the task asks for:

1. If the task names an output file or format, write exactly that (path, file type, top-level keys, field names). Otherwise write JSON with a top-level `plan` list of the day objects above, plus `total_cost`, to the location the task gives, or just return it.
2. Copy names exactly from the plan; do not "tidy" restaurant, attraction, or accommodation names (odd spacing and symbols are part of the sandbox names and must match).
3. If violations remain (validation gave up), say which constraints the plan could not meet and why (e.g. no flight on that date, cheapest feasible plan exceeds the budget) instead of claiming success.

Post `final_answer` (string): a short summary — route and dates, transportation, total cost vs budget, and where the plan was written.
