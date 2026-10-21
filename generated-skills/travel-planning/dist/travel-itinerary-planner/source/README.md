# Source and provenance: travel-itinerary-planner

## What was compiled

Six curated Agent Skills, copied verbatim into this folder:

| Folder | Original role |
|---|---|
| `search-cities/` (SKILL.md, scripts/search_cities.py) | state → cities from `background/citySet_with_states.txt` |
| `search-accommodations/` (SKILL.md, scripts/search_accommodations.py) | lodging by city |
| `search-attractions/` (SKILL.md, scripts/search_attractions.py) | attractions by city |
| `search-restaurants/` (SKILL.md, scripts/search_restaurants.py) | restaurants by city |
| `search-driving-distance/` (SKILL.md, scripts/search_driving_distance.py) | driving/taxi duration, distance, cost |
| `search-flights/` (SKILL.md, scripts/search_flights.py) | flights by origin/destination/date |

`task-instruction-example.md` is the task statement the downstream agent gets
(a 7-day Minneapolis → Ohio trip for two, pet-friendly, no flights, $5,100,
`/app/output/itinerary.json`). It was used to fix the output format and to test
the skill. No answer from it is hardcoded.

The six skills are thin wrappers around one dataset, the TravelPlanner
benchmark sandbox. Their names (`search_*`) are the ones the output's
`tool_called` must list. Itinerary validity rules (commonsense and hard
constraints) do not appear in the sources. They come from the TravelPlanner
evaluation conventions this dataset was built for. They were added because an
itinerary that ignores them fails even if every search was right. They live in
`scripts/travel.py validate` and `references/planning-rules.md`.

## Intent

One skill takes a natural-language trip request to a validated itinerary JSON.
It searches the database, picks a city route, transport, lodging, meals, and
attractions, checks every rule, and writes the plan.

## Component kinds (and why)

| Component | Kind | Why |
|---|---|---|
| Six searches → `scripts/travel.py cities/accommodations/attractions/restaurants/distance/flights` | execution | Pure lookups over fixed files. They merge into one script because they share data loading, and one CLI is simpler than six importable modules. |
| Classify the request (dest_type, needs_* house rules, room_type, transportation) | decision | The answer space is fixed by the dataset vocabulary, but reading it from free text takes judgment. Typed answers feed `constraints.json`. |
| Write `constraints.json` | client task | Extracting free values (origin, dates, budget, people, cuisines) from prose. The script then validates it against database vocabularies, so typos fail fast. |
| Route enumeration, lodging filter (house rules, room type, min nights, rooms = ceil(people/occupancy)), transport-family choice, cuisine-covering restaurant assignment, attractions, costs → `draft` | execution | Deterministic combinatorics, thresholds, and arithmetic. Doing this by hand is slow and error-prone (for example, 120 Ohio routes × 2 modes). |
| Rule check and budget → `validate` | execution | Fixed rules over structured data. This is the validation loop. |
| Review and adjust the draft | client task | Stated soft preferences (attraction types, comfort vs. cheapest) need judgment. The edits go back through `validate`. |
| Write output and summarize | client task | Placing the file and producing the user-facing synthesis. |

## Line-by-line completeness check

| Source content | Where it lives now |
|---|---|
| Each SKILL.md description (what each search does, when to use it) | SKILL.md description, Trigger When item 4, Procedure step 3 commands |
| `pip install pandas` / `numpy requests` installation | frontmatter `compatibility`, script header, Setup check. numpy is pulled in by pandas. `requests` was only for the never-implemented online mode (dropped below). |
| Quick Start Python class usage (`Accommodations().run("Seattle")`, etc.) | Replaced by the CLI subcommands with the same inputs (step 3) |
| `_find_data_path`: `/app/data` first, else relative `../../../data` | `find_data_dir`: `--data-dir`, `$TRAVEL_DATA_DIR`, `/app/data`, `./data`, relative. Note that search_flights hardcoded only the relative path. That bug is fixed. |
| Accommodations: column subset + `dropna()` + city strip + case-insensitive match | `ACC_COLUMNS`, `DB.accommodations`, `DB.lodging`. The dropna semantics are kept on purpose (see Gotchas: rows the source tool can't return don't exist). |
| Attractions: columns + dropna + case-insensitive City | `ATTR_COLUMNS`, `DB.attractions`, `cmd_search` |
| Restaurants: columns + dropna + case-insensitive City | `REST_COLUMNS`, `DB.restaurants`, `cmd_search`; `--cuisines` filter added |
| Cities: tab-separated city/state, skip malformed or blank lines, case-insensitive state, "Invalid state." | `DB.city_state`, `cities_in_state`, `cmd_search` (same message) |
| Driving: strip text before "(", parse "1,234 km", `driving` → int(km×0.05), `taxi` → int(km), duration containing "day" → no valid info, "no valid information." message, output line format | `strip_paren`, `DB.leg`, `cmd_search distance` (same message). Mode is named `self-driving`/`taxi`. The vehicle multiplier (ceil(people/5) cars, ceil(people/4) taxis) comes from the evaluation conventions. |
| Distance CSV: dropna on origin/destination/duration/distance; first match wins | `DB.distances` (drop_duplicates keeps first) |
| Flights: rename `Unnamed: 0` → Flight Number, column subset, dropna, exact match on OriginCityName/DestCityName/FlightDate, "There is no flight from … on …" message | `DB.flights`, `cheapest_flight`, `cmd_search flights` (same message) |
| `run_for_annotation` (strip parenthetical before lookup) in flights/restaurants | `strip_paren` is applied to every city in lookups and validation |
| `get_city_set` (flights/restaurants) | Validation uses the background city set plus per-file existence checks |
| Error messages for missing args/files | argparse `required=True`; `find_data_dir` error text |
| Task instruction: output keys, 7 day objects, `"-"` for skipped, `;`-terminated attractions, `"from A to B"`, `Self-driving: from A to B`, no flights, pet-friendly lodging, `tool_called` names, use DB data only | SKILL.md steps 2, 5, and 7, plus Gotchas; `draft` output format; `validate` checks; references/planning-rules.md "Itinerary shape" |

## Deliberate drops

| Dropped | Rationale |
|---|---|
| search-accommodations SKILL.md fragment "Notice all the" | The sentence is truncated in the source and carries no recoverable instruction. |
| `city_normalizer` / `state_normalizer` constructor hooks | They default to the identity function. They only served as a programmatic extension point. Trimming, case folding, and parenthesis stripping are built in. |
| "X loaded." prints on construction | Noise for a CLI. |
| Google Distance Matrix online mode (`--api-key`, `subscription_key`) | Never implemented in the source (always local). The container is offline, and planning must use the bundled data only. |
| Per-file `--path` overrides | Replaced by a single `--data-dir`, since all files share one root. |
| Source wording "There are no accommodations in this city." / "There is no attraction in this city." / "There is no restaurant in this city." | Collapsed to "No results." Same meaning. |
| Python-import Quick Start | Replaced by the CLI. The classes aren't needed by an agent that runs commands. |

## Design choices worth knowing

- The task example shows day 1's `current_city` as `"Minneapolis"`, but the instruction allows `"from A to B"` on moving days. The skill uses `"from A to B"` because it is the TravelPlanner convention, and it lets meals and lodging belong to either endpoint.
- The last day's accommodation is `"-"`: the trip ends at home, and budget counts nights only.
- `draft` minimizes cost (transport + lodging first, then meals). It prefers restaurants serving requested cuisines and covers each required cuisine outside the origin. Upgrades are left to the review step.
