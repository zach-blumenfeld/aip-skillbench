# Source — search-flights (AIP conversion)

## What this skill is

Filters the bundled cleaned flights dataset
(`/app/data/flights/clean_Flights_2022.csv`) by origin city, destination city,
and departure date and returns the matching flight rows. Backs the "do flights
exist for this leg / what are they?" decision in a multi-city itinerary
workflow. Pairs with the other travel-planning sibling skills (search-cities,
search-restaurants, search-attractions, search-driving-distance,
search-accommodations).

## Provenance

Adapted from
`vendor/skillsbench/tasks/travel-planning/environment/skills/search-flights/SKILL.md`
(captured verbatim as `ORIGINAL_SKILL.md` in this directory) and the
companion implementation at
`vendor/skillsbench/tasks/travel-planning/environment/skills/search-flights/scripts/search_flights.py`.

The original SKILL.md is a near-empty stub — an install line and a Python
Quick Start snippet, no behavioural documentation — so most of the AIP body
is recovered from the script's actual behaviour rather than the prose.

## Schema choice

- `procedure.schema.json` (procedure category) — the skill is a small,
  script-backed workflow (parse request → run lookup → interpret the
  DataFrame/sentinel-string return). No new schema required.

## Source → AIP mapping

| Original SKILL.md content                                          | AIP location                                                                |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------- |
| Skill name + one-line description                                  | `name`, `description` frontmatter                                           |
| Title "Search Flights" + "Filter the cleaned flights CSV..."       | `purpose`                                                                   |
| Installation: `pip install pandas`                                 | `compatibility` frontmatter (Python 3.9+ and pandas)                        |
| Quick Start usage snippet (`Flights().run(origin, dest, date)`)    | `scenarios[0]` + `lookup-flights` step description                          |
| Implementation behaviour (column projection, exact-match filter)   | `scripts/search_flights.py` (preserved) + `lookup-flights` step             |
| Sentinel return strings on empty data / no match                   | `interpret-result` step + `anti_patterns`                                   |
| Default data path resolution (`/app/data` → relative fallback)     | `scripts/search_flights.py` (added for container/local parity)              |

## Notable additions vs. the original

The original SKILL.md does not document:

- **Return type is a union.** `Flights.run` returns either a pandas
  `DataFrame` (matching rows) or one of two sentinel strings:
  `"No flight data is available."` (empty dataset) or
  `"There is no flight from {origin} to {destination} on {date}."`
  (no match). The AIP body says so explicitly and `interpret-result`
  gates the three branches.
- **Matching is exact on the city columns and the date column.** No
  case-folding, no whitespace stripping beyond what the caller does.
  Origin/destination are compared verbatim against the CSV's
  `OriginCityName`/`DestCityName` columns. The AIP body and
  `anti_patterns` flag this so the agent does not pass
  `"new york"` or `"New York, NY"` and expect a hit.
- **Date format is ISO `YYYY-MM-DD`.** The CSV's `FlightDate` column is
  ISO-formatted and the comparison is string equality — so
  `"2022-01-15"` matches, `"01/15/2022"` does not. Captured explicitly
  in the body.
- **The dataset is 2022 only.** ~380k rows of U.S. domestic flights from
  calendar year 2022. Out-of-year dates will silently return the
  no-match sentinel. The AIP body notes the dataset scope so the agent
  reports "not in dataset" instead of fabricating flights.
- **`Flights()` is expensive to construct.** It reads, projects, and
  drops NaNs from the full CSV on `__init__` and prints `Flights API
  loaded.` to stdout. Reuse a single instance per session rather than
  reconstructing in a hot per-leg loop.
- **City naming convention.** Cities are bare names without a state
  qualifier — `"New York"`, `"Los Angeles"`, `"Newark"`. Pass the
  bare city name; strip any trailing `" (XX)"` qualifier first.
- **A `run_for_annotation` helper exists** that strips a trailing
  parenthetical (e.g., `"Seattle (WA)"` → `"Seattle"`) before
  delegating to `run`. Useful when the caller hasn't pre-stripped the
  qualifier.
- **Data path resolution.** The bundled script was edited to prefer
  `/app/data/flights/clean_Flights_2022.csv` (container) and fall back
  to a script-relative path, mirroring the search-cities and
  search-driving-distance siblings. The original assumed the
  task-container layout only; the AIP-edition handles both cases so the
  skill is runnable outside the container with `--path`.

## Deliberate drops

None of the original content is dropped. The two short prose blocks
(Installation, Quick Start) map cleanly onto `compatibility` and
`scenarios[0]`.
