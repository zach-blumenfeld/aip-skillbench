# source/ — search-flights AIP conversion

## Inputs

- `curated-SKILL.md` — original curated Agent Skill from
  `vendor/skillsbench/tasks/travel-planning/environment/skills/search-flights/SKILL.md`.
  Tiny: a one-liner description, a pip install hint, and a Python quick-start
  snippet. No anti-patterns, no input validation rules, no schema for the
  returned DataFrame.
- `procedure.schema.json` — bundled copy of the AIP `procedure` schema
  (`v0.3a3`). Picked because the skill is an execution graph: load CSV →
  filter by (origin, destination, date) → return rows or a "no match"
  string. Script-backed step + clear inputs/outputs maps cleanly onto the
  procedure shape.

## Schema choice

`procedure` over a bespoke schema — the skill is a single procedure with
one script-backed step. No need to invent a new schema family.

## Script choice

`scripts/search_flights.py` is copied **verbatim** from the curated skill.
The class already exposes the deterministic filter (exact-match on
`OriginCityName`, `DestCityName`, `FlightDate`) and a CLI for direct
invocation. Rewriting it would only risk drift from the dataset the task
mounts at `environment/data/flights/clean_Flights_2022.csv` (the script
resolves that path relative to its own location, three directories up).

Domain logic in the script (kept as script, not prose):
- CSV column whitelist + drop-NA cleanup.
- Exact equality match on city names and date — no fuzzy matching.
- Empty-result branch returns a sentinel string, not an empty DataFrame.
- Optional `city_normalizer` hook (defaults to identity) for callers that
  want to strip parenthetical state suffixes etc.

## Specialized knowledge added beyond the curated SKILL.md

The curated file tells the agent *that* a `Flights` class exists. The AIP
body adds the operational knowledge an autonomous agent needs to actually
use it inside the travel-planning task:

- City-name format gotcha — the CSV stores bare city names ("Newark",
  "New Orleans"), not "Newark, NJ". Passing "Newark (NJ)" or
  "Newark, NJ" returns the no-flight sentinel even though the route
  exists.
- Date format — `YYYY-MM-DD`, exact string match against `FlightDate`.
- Dataset scope — only US routes that appear in
  `clean_Flights_2022.csv` (2022 only). Routes outside the dataset
  return the sentinel.
- Return-type discriminator — agent must branch on `isinstance(result,
  str)` vs DataFrame; a string means "no match", not an error.
- CLI invocation form for agents that prefer subprocess over Python
  import.
- The `search-flights` skill is for *checking availability and prices*;
  it does not produce the itinerary or pick the cheapest option — that
  is the calling agent's job.

## Deliberate drops

- The pip-install hint (`pip install pandas`) is dropped from the body.
  The task environment ships pandas via the task `Dockerfile`; restating
  the install in the SKILL adds tokens without changing behavior.
- The Python quick-start snippet is rolled into the `usage` step rather
  than repeated verbatim.

## Validation

```bash
uv run /Users/zach/dev/aip-skillbench/.claude/skills/aip/scripts/validate.py \
  /Users/zach/dev/aip-skillbench/generated-skills/travel-planning/aip-from-curated/search-flights
```
