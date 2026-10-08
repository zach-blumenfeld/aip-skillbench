# Source and provenance — travel-planning

## Sources (copied verbatim in this folder)

| Folder | Original skill | What it contributed |
|---|---|---|
| `search-cities/` | SKILL.md + `scripts/search_cities.py` | state → cities from `background/citySet_with_states.txt` (tab-separated), case-insensitive state match, "Invalid state." |
| `search-flights/` | SKILL.md + `scripts/search_flights.py` | flight columns, `Unnamed: 0` → `Flight Number` rename, `dropna`, exact origin/destination/date match, parenthesis stripping (`run_for_annotation`) |
| `search-driving-distance/` | SKILL.md + `scripts/search_driving_distance.py` | distance matrix columns, "day" durations invalid, cost self-driving `int(km*0.05)`, taxi `int(km)`, output string `"<mode>, from A to B, duration: …, distance: …, cost: N"` |
| `search-accommodations/` | SKILL.md + `scripts/search_accommodations.py` | selected columns, `dropna`, case-insensitive city match |
| `search-restaurants/` | SKILL.md + `scripts/search_restaurants.py` | selected columns, `dropna`, case-insensitive city match |
| `search-attractions/` | SKILL.md + `scripts/search_attractions.py` | selected columns, `dropna`, case-insensitive city match |

Environment facts used: `inputs/environment/Dockerfile` (python 3.12-slim, pandas/numpy/requests,
data copied to `/app/data`) and `MANIFEST.md` plus the data files themselves (column order,
delimiters, the empty `cost` column in `distance.csv`, ~700 accommodations with empty
`house_rules`, flight date range 2022-01-01 … 2022-07-31, "24:00" and overnight arrival times).

Added domain knowledge not in the sources: the six tools are the TravelPlanner sandbox
(Xie et al., 2024). Its plan format, commonsense constraints (sandbox entities, completeness,
current-city, route, no repeats, no flight + self-driving mix, minimum nights) and hard
constraints (house rule, room type, cuisine, transportation, budget, with the per-person /
per-vehicle / per-room cost formulas) are encoded in `scripts/validate_plan.py`,
`assets/review_plan.md`, and `references/planning-rules.md`, because an agent planning a trip
over these tools is judged by them.

## Intent

The curated skills are six lookup tools that together serve one workflow: plan a trip. The
AIP skill compiles them into one graph: parse the request → search and draft (script) →
(if infeasible: re-read the request once) → agent review → validate (script) → loop on violations → deliver.

## Step-kind choices

| Step | Kind | Why |
|---|---|---|
| parse-request | client_task | Free-text (or JSON) request → typed query; requires language understanding and mapping phrases to constraint values; output is structured state, not prose. |
| plan-trip | execution | All lookups, filters (room type, house rule, minimum nights), cost formulas, route/night-split/transport enumeration, cuisine coverage, and meal/attraction placement are deterministic over the data — scripted so nothing is guessed. |
| check-feasibility | router | Branches on the planner's `planner_outcome`: feasible → review; infeasible → revise-query once; infeasible-final (2nd attempt) → review, where the agent builds the closest plan by hand. |
| revise-query | client_task | Diagnosing an infeasible search means re-reading the request (parse slip, over-strict constraint reading such as "at least a private room") against per-city diagnostics; output is a corrected query. Added after fresh-agent testing hit this case. |
| review-plan | client_task | The agent must reconcile the draft with request details the schema cannot capture and repair violations; generation of a plan. |
| validate-plan | execution | Every constraint is a deterministic rule over the plan and data; also computes total cost and counts attempts. |
| check-validation | router | Branches on the validator's `validation_outcome` (pass / fail / give-up after 3 attempts) so the fix loop terminates. |
| deliver | client_task | Output path/format is task-specific; the agent writes it and summarizes. |

No decision step: every judgment that has a fixed answer space (destination is a state or a
city, constraint satisfaction, budget) is computed by the scripts from the data; the remaining
judgments (parsing, request-specific edits) produce structured or generated output.

Scripts use only the standard library (csv/json) so they run under the container's Python and
under any bare interpreter; the pandas semantics they mirror (`dropna`, default NA strings) are
reimplemented in `scripts/travel_db.py`, which also exposes the six original lookups as a CLI.
Data discovery order: `data_dir` input, `$TRAVEL_DATA_DIR`, `/app/data`, `/root/data`,
`/root/environment/data`, `/root`, `/data`, `/workspace/data`, `./data`, then a depth-4 search.

## Completeness check (source item → where it lives)

- search-cities description "validate state inputs or expand destination choices" → `plan_trip.py` (state → candidate cities, city fallback), CLI `cities`.
- Cities tab-separated parse, skip malformed/empty lines, case-insensitive match, "Invalid state." → `travel_db.load_city_states`, `cities_for_state`, CLI.
- `/app/data` container path first, then relative path → `travel_db.find_data_dir` (extended with more candidates).
- Flights columns, rename, dropna, exact match, no-flight message, `run_for_annotation` parenthesis stripping, `get_city_set` → `travel_db.load_flights`, `search_flights`, CLI message; city set used implicitly via flight index.
- Driving: `_extract_before_parenthesis`, `_parse_distance_km`, `_compute_cost` (driving 0.05/km, taxi 1/km), "day" → no info, `values[0]` first match, output string format, "no valid information" → `travel_db.search_distance`, `load_distances`, planner transport strings, validator, references.
- Driving mode default "driving"; CLI `--mode` → CLI default `self-driving` (same cost rule: any mode containing "driving").
- Accommodations wanted columns, dropna, strip city, case-insensitive, "There are no accommodations in this city." → `travel_db.load_accommodations`, `by_city`, CLI.
- Restaurants columns, dropna, strip, case-insensitive, "There is no restaurant in this city.", `run_for_annotation`, `get_city_set` → `travel_db.load_restaurants`, CLI.
- Attractions columns, dropna, strip, case-insensitive, "There is no attraction in this city." → `travel_db.load_attractions`, CLI.
- SKILL.md descriptions "recommend places to stay / filter lodging before building an itinerary", "comparing ground travel options or validating itinerary legs", "proposing flight options or checking whether a route/date combination exists", "recommending places to eat", "points of interest / sightseeing" → the planner, review template, and trigger_when.
- Quick-start examples (Seattle, Portland, New York → Los Angeles 2022-01-15, San Francisco, …) → CLI examples in `references/planning-rules.md`.

## Deliberate drops

- **Installation sections** (`pip install pandas numpy requests`): scripts are stdlib-only; the container already has these packages. Nothing to install.
- **Python class APIs** (`Cities()`, `Flights().run(...)`, constructor `city_normalizer`/`state_normalizer` hooks): replaced by functions and a CLI; the normalizer hooks were identity by default and unused.
- **Google Distance Matrix API key / "online mode"** (`subscription_key`, `--api-key`): the original never calls the API (local CSV only); dropping it changes no result.
- **"Cities loaded." / "Flights API loaded." banners**: stdout noise; scripts must print one JSON object.
- **Returning pandas DataFrames / `to_string` tables**: lookups return JSON rows with the same columns.
- **search-accommodations SKILL.md "Notice all the"**: the sentence is truncated in the source; no recoverable instruction.
- **search-flights default path without the `/app/data` check**: superseded by the shared data discovery.
