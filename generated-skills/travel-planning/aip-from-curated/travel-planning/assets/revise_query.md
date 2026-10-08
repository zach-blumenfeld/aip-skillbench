# The planner found no feasible trip

Request:

{request}

Parsed query: origin {origin}, destination {destination}, start {start_date}, {days} days, {visiting_city_number} cities, {people_number} people, budget {budget}, constraints {local_constraint}, data folder "{data_dir}".

Planner notes: {planner_notes}

Per destination city — what exists and what blocked it: {diagnostics}

Find the cause and re-post the full query (origin, destination, start_date, days, visiting_city_number, people_number, budget, local_constraint, data_dir):

1. Data folder not found: set `data_dir` to the folder holding `background/citySet_with_states.txt` (check the task text, /app/data, /root/data, /root).
2. A parse error: wrong city spelling, wrong date or year, wrong day count, state given as a city. Fix it.
3. A constraint read more strictly than the request says. Re-read the wording: "at least a private room" means "not shared room", not "private room"; a wish ("would be nice") is not a hard constraint. Loosen it only when the request's words allow it.
4. Otherwise the request is infeasible as written. Re-post the query unchanged; the run then goes on to build the closest plan by hand and report what cannot be met.

Use `python scripts/travel_db.py ...` (see `references/planning-rules.md`) to confirm a cause before changing anything.
