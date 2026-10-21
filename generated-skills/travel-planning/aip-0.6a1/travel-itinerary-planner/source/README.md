# Source and provenance

Compiled from six curated Agent Skills, copied verbatim into this folder:

| Source | Files |
|---|---|
| `search-cities/` | `SKILL.md`, `scripts/search_cities.py` |
| `search-accommodations/` | `SKILL.md`, `scripts/search_accommodations.py` |
| `search-restaurants/` | `SKILL.md`, `scripts/search_restaurants.py` |
| `search-attractions/` | `SKILL.md`, `scripts/search_attractions.py` |
| `search-driving-distance/` | `SKILL.md`, `scripts/search_driving_distance.py` |
| `search-flights/` | `SKILL.md`, `scripts/search_flights.py` |

Together they describe one workflow: build a round-trip travel itinerary (TravelPlanner
style) from a bundled sandbox database, mounted at `/app/data` in the task container
(`python:3.12-slim` + pandas 2.2.2, numpy 1.26.4, requests 2.31.0). The task statement asks for
`/app/output/itinerary.json` with a `plan` (one object per day: `day`, `current_city`,
`transportation`, `breakfast`, `lunch`, `dinner`, `attraction`, `accommodation`) and a
`tool_called` list naming the search skills used.

## Intent

The sources are six thin search wrappers; the planning knowledge (route shape, budget rules,
constraint vocabulary, format) is what an agent lacks. The compiled skill keeps every search
behaviour and adds the planner and checker around it, so a run is: structure the request ->
search everything in one script -> plan in a script -> verify -> write. The agent only does
work that needs language understanding (parsing the request) or a repair it cannot avoid.

## Component-kind choices

| Step | Kind | Why |
|---|---|---|
| `parse-request` | client_task | Extracting origin, dates, people, budget and constraint vocabulary from free text is generation; the output is a fixed-shape object so everything downstream is deterministic. |
| `search-candidates` | execution | All six searches are deterministic table filters (the source scripts). House-rule / room-type filtering is a fixed rule. |
| `build-plan` | execution | Route choice, night split, min-night check, cuisine coverage, uniqueness and budget arithmetic are deterministic optimisation over structured data. |
| `route-plan` | router | Branches on the script's `plan_status`; no judgment needed. |
| `write-itinerary` / `write-repaired` | execution | Normalising the output shape and re-checking against the database are fixed rules. One script serves both; it names its output by which plan key it received. |
| `repair-itinerary` | client_task | Only reached when no generated plan passes (e.g. budget below the cheapest feasible trip). Trading off which preference to relax needs the agent. |

No decision step: after parsing, every branch point is a computed fact (passes checks or not).

## Mapping of source content

- `search_cities.py` (tab-separated city/state file, case-insensitive state match, "Invalid state.") -> `scripts/travel_db.py` `city_state_map` / `search_cities`; used by `search_candidates.py` when `dest` is a state.
- `search_accommodations.py` (column subset NAME, price, room type, house_rules, minimum nights, maximum occupancy, review rate number, city; `dropna`; case-insensitive city) -> `travel_db.search_accommodations`; house-rule/room-type filter in `travel_db.accommodation_ok`.
- `search_restaurants.py` (Name, Average Cost, Cuisines, Aggregate Rating, City; `dropna`; parenthesis stripping) -> `travel_db.search_restaurants`.
- `search_attractions.py` (Name, Latitude, Longitude, Address, Phone, Website, City; `dropna`) -> `travel_db.search_attractions`.
- `search_driving_distance.py` (exact origin/destination match, parenthesis stripping, "day" durations = no valid info, cost `int(km*0.05)` driving / `int(km)` taxi) -> `travel_db.search_driving_distance`, `leg_cost`.
- `search_flights.py` (rename `Unnamed: 0`, column subset, exact origin/destination/date match) -> `travel_db.search_flights`.
- Each source's "Quick Start" class usage -> the `travel_db.py` CLI (`python travel_db.py restaurants --city X`) referenced in the repair template.
- "Installation: pip install pandas" -> `requires.packages: [pandas]`. numpy/requests are in the container but no script imports them.
- Task-level knowledge not in the sources but needed (from the instruction and the TravelPlanner benchmark conventions): cost formulas per mode and per room, minimum-nights rule, no repeated restaurants/attractions, no self-driving mixed with taxi/flight, cuisine coverage in destination cities only, "Name, City" format -> `scripts/plan_check.py` and `references/itinerary-rules.md`.

## Deliberate-drop log

| Dropped | Rationale |
|---|---|
| `city_normalizer` / `state_normalizer` constructor hooks | Extension points with identity defaults; `travel_db.canonical_city` does the only normalisation needed. |
| Hard-coded data path discovery (`/app/data` first, else relative to the script) | Replaced by the `data_dir` start input, default `/app/data`. The flights script's default path (relative only, would miss `/app/data`) was a bug and is not carried. |
| Google Distance Matrix API key option (`--api-key`, "online mode") | The class never calls the API; local CSV only, and the container has no network contract. |
| `run_for_annotation` variants | Only strip parenthetical text, which every search here already does. |
| `get_city_set` helpers | Not used by the workflow; city lists come from the background file. |
| Human-readable string returns ("There is no restaurant in this city.", `to_string` printing, "X loaded." banners) | Scripts exchange JSON; empty results are represented as empty lists / excluded cities with a reason. The CLI prints JSON. |
| The truncated sentence "Notice all the" in search-accommodations SKILL.md | Incomplete in the source; no recoverable content. |
| Attraction Latitude, Longitude, Phone, Website in the planner's candidates | Still loaded (and used for `dropna`, exactly as the source) and printed by the CLI; the planner only needs name and address, and carrying them would bloat the state. |
| Source SKILL.md example cities (Seattle, New York, California, Portland...) | Illustrative only. |

## Design notes / assumptions

- Lodging rows with a blank `house_rules` are dropped exactly as the source loader does, so the planner never books an entity outside the sandbox the checker uses.
- Nights split evenly across cities; legs of >= 6 h get a lighter travel day (see the reference). These are presentation choices; the checks do not depend on them.
- Transport strategies are all-self-driving, all-taxi, or flights with taxi fallback, which can never mix self-driving with other modes.
- `transportation` strings follow the task statement (`"Self-driving: from A to B"`); duration, distance and cost per leg are in `plan_report`.

## Functional test record

`aip run` on the task query (7 days, Minneapolis -> 3 Ohio cities, 2 people, $5,100, pets,
4 cuisines, no flights) took the `ok` branch: Toledo -> Akron -> Dayton, all self-driving,
pet-friendly lodging meeting minimum nights, all four cuisines covered, total $4,809, zero
violations; independently re-verified against the raw CSVs. The same query with a $1,500 budget
took the `needs_repair` branch (cheapest feasible trip is $1,601 even with meals cut to the three
cuisine-covering ones); the repaired plan was written with the remaining budget violation reported.
Scripts were also run under Python 3.12 + pandas 2.2.2 + numpy 1.26.4 (the container stack) with identical output,
and against a 3-day single-city trip with flights allowed and a 5-day no-self-driving trip (flight+taxi).
