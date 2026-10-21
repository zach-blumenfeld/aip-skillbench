---
name: travel-itinerary-planner
description: Build a multi-day travel itinerary (TravelPlanner-style JSON plan) from the bundled travel database. The skill searches cities, accommodations, restaurants, attractions, driving/taxi distances, and flights, then drafts the cheapest valid route. It enforces house rules (pets, smoking, parties, children, visitors), room type, cuisines, transport bans, minimum nights, no-repeat and same-city rules, and the budget. Use for requests like "7-day trip for two from Minneapolis covering 3 cities in Ohio, budget $5,100, pet-friendly, no flights".
compatibility: Python >= 3.10; pandas (container ships pandas==2.2.2, numpy==1.26.4). Offline; reads the dataset under /app/data (or --data-dir / $TRAVEL_DATA_DIR).
---

# Travel Itinerary Planner

## Trigger When

1. A task asks for a day-by-day travel itinerary or plan saved as JSON, such as `/app/output/itinerary.json` with `plan` and `tool_called`.
2. Planning a trip that must use only the bundled database files (accommodations, restaurants, attractions, distance matrix, flights, city/state lists), not memory.
3. A request combines an origin, a destination state or city, dates or a day count, a group size, a budget, and constraints such as pet-friendly lodging, room type, cuisines, or "no flights" / "no self-driving".
4. Any time you would otherwise use `search_cities`, `search_accommodations`, `search_restaurants`, `search_attractions`, `search_driving_distance`, or `search_flights`.

## Purpose

This skill turns a natural-language trip request into a validated itinerary built only from the bundled travel database. It replaces six separate search tools with one script. That script searches, enumerates every city route, and picks the cheapest transport and the cheapest lodging that meet the rules. It then assigns distinct restaurants that cover the requested cuisines, adds attractions, and writes the plan. A validator re-checks the plan against the database. The validator applies the evaluation rules that are easy to miss: minimum nights, no mixing self-driving with other modes, `"Name, City"` entries, cuisine coverage outside the origin, cost multiplied by occupancy, and the budget.

## Setup

Before the first script, run `python3 -c "import pandas"`. If it fails, report that pandas is missing (the only dependency). Run every command from the skill folder. Data is found automatically at `/app/data`; otherwise pass `--data-dir DIR` before the subcommand. Each search call is logged so `draft` can fill `tool_called`. Start every task with:

```bash
python3 scripts/travel.py reset-log
```

## Procedure

Progress:
- [ ] 1. Classify the request (decision)
- [ ] 2. Write `/tmp/trip/constraints.json` (client task)
- [ ] 3. Explore with search commands (execution)
- [ ] 4. Draft the plan (execution)
- [ ] 5. Review and adjust (client task)
- [ ] 6. Validate until clean (execution)
- [ ] 7. Write the output (client task)

### 1. Classify the request (decision)

Input: the user's request text. Answer every question in one pass. A false "yes" on a house-rule or room-type question shrinks the lodging pool, and a false "no" breaks a hard constraint. Reconsider close calls: only explicit needs count (for example, "we bring our dog" counts as pets).

```yaml
dest_type:
  type: choice
  instructions: Is the destination a US state (cities chosen by you) or one named city?
  criteria:
    state: A state is named ("three cities in Ohio", "visit Texas").
    city: A single city is named ("trip to Chicago").
needs_pets:
  type: noul
  instructions: Do travelers bring pets, i.e. need pet-friendly lodging?
  criteria:
    true: Pets, dogs, cats, or pet-friendly lodging are mentioned as part of the trip.
    false: No animals mentioned.
needs_smoking:
  type: noul
  instructions: Do travelers need to smoke in the lodging?
  criteria:
    true: Smoking or smoking-allowed lodging is requested.
    false: Smoking not mentioned.
needs_parties:
  type: noul
  instructions: Do travelers want lodging that allows parties?
  criteria:
    true: Hosting parties or gatherings at the lodging is requested.
    false: Not mentioned.
needs_children_under_10:
  type: noul
  instructions: Are children under 10 travelling?
  criteria:
    true: Young kids or children under 10 are in the group.
    false: Adults only, or children's ages not stated as under 10.
needs_visitors:
  type: noul
  instructions: Will travelers receive visitors at the lodging?
  criteria:
    true: Guests or visitors coming to the lodging are mentioned.
    false: Not mentioned.
room_type:
  type: choice
  instructions: Which room type does the request require?
  criteria:
    entire room: Entire home/apartment explicitly requested.
    private room: A private room explicitly requested.
    shared room: A shared room explicitly requested.
    not shared room: Only "not shared" / "no shared rooms" stated.
    none: No room type requirement.
transportation:
  type: choice
  instructions: Which transport mode does the user forbid?
  criteria:
    no flight: Prefers not to fly / no flights.
    no self-driving: Will not drive themselves.
    none: No transport restriction.
```

### 2. Write `/tmp/trip/constraints.json` (client task)

Fill this in from the request and the step-1 answers (`mkdir -p /tmp/trip`). Keep working files there, never inside the skill.

```json
{"org": "Minneapolis", "dest": "Ohio", "dest_type": "state", "days": 7, "visiting_city_number": 3,
 "date": "2022-03-17", "people_number": 2, "budget": 5100,
 "local_constraint": {"house rule": ["pets"], "room type": null,
                      "cuisine": ["American", "Mediterranean", "Chinese", "Italian"],
                      "transportation": "no flight"}}
```

- `house rule`: list each `needs_*` that is true, as `pets`, `smoking`, `parties`, `children under 10`, or `visitors`. Use `[]` if none.
- `room type` / `transportation`: the step-1 label, or `null` for `none`.
- `cuisine`: the cuisines the user names, using database labels. Treat "preferably" as required.
- `date`: the start date `YYYY-MM-DD` (a list of dates is also accepted). `people_number` defaults to 1 when unstated.
- `visiting_city_number`: the stated count. If it isn't stated, omit it to get 3→1, 5→2, 7→3 by day count.

### 3. Explore (execution)

Run the searches that ground the plan. These also record `tool_called` names:

```bash
python3 scripts/travel.py cities --state Ohio                       # dest_type == state
python3 scripts/travel.py accommodations --city Toledo --rules pets --people 2 --nights 2
python3 scripts/travel.py restaurants --city Toledo --cuisines american,italian
python3 scripts/travel.py attractions --city Toledo
python3 scripts/travel.py distance --origin Minneapolis --destination Toledo --mode self-driving --people 2
python3 scripts/travel.py flights --origin A --destination B --date 2022-03-17   # only if flights allowed
```

Skip `flights` when `transportation` is `no flight`, so the search isn't listed in `tool_called`.

### 4. Draft (execution)

```bash
python3 scripts/travel.py draft --constraints /tmp/trip/constraints.json --out /tmp/trip/draft.json
```

The command prints JSON with `status`, `route`, `nights`, `estimated_total_cost`, and `budget`, and writes the full `{plan, tool_called}` file.

- Exit 0, `ok`: continue to step 5.
- Exit 3, `over_budget`: the cheapest valid plan still exceeds the budget. Cut cost by changing travel-day meals to `"-"` (step 5), then validate. If it's still over, report the shortfall.
- Exit 2, `infeasible`: read `references/planning-rules.md` § "When `draft` says infeasible". Re-run with `--max-routes 500` for cuisine failures. Otherwise, build the closest plan by hand with step-3 searches and say which constraint can't be met.
- Exit 1, `ERROR in constraints`: fix the field it names (a cuisine label, rule spelling, or unknown city or state) and re-run.

### 5. Review and adjust (client task)

Read `/tmp/trip/draft.json`. The draft is the cheapest valid option, so change it only to match a stated preference it missed. Examples are a requested attraction type, an upscale stay when the budget allows, or meals on a travel day that are unrealistic for the drive. Every replacement must come from a step-3 search for that day's city. Read `references/planning-rules.md` before hand-editing.

### 6. Validate (execution)

```bash
python3 scripts/travel.py validate --constraints /tmp/trip/constraints.json --plan /tmp/trip/draft.json
```

Exit 0 means `"valid": true`; the output also shows the cost breakdown. Exit 1 lists `errors`. Fix each one, then re-run until it's clean. Don't write the output while errors remain unless the request is infeasible, in which case report what's unmet.

### 7. Output (client task)

Copy the validated file to the task's output path (for example, `mkdir -p /app/output && cp /tmp/trip/draft.json /app/output/itinerary.json`). Confirm that `plan` has exactly `days` entries and that `tool_called` lists the search tools you actually used. Then summarize the route, the lodging, and the total cost against the budget.

## Gotchas

- Use only `"Name, City"` strings copied from search output. Names from memory, or names with a city tacked on, fail the database check.
- The lodging dataset is all short-term rentals, and their names often mention another city ("Brooklyn brownstone" in Cincinnati). The `city` column decides location.
- Listings, attractions, or restaurants with any blank searched field are invisible to the original search tools, so the scripts exclude them. Don't add them by reading the CSV directly.
- `minimum nights` must be at most the consecutive nights you stay there. A 60-dollar room with a 3-night minimum is unusable for a 2-night stop.
- Lodging cost is per room: two travelers in a `maximum occupancy` 1 listing pay for 2 rooms.
- Self-driving anywhere means no taxi or flight anywhere. Distance-matrix lookups are case-sensitive and directional (A→B and B→A are separate rows).
- Cuisine coverage counts only restaurants outside the origin city. Origin-city meals are fine but don't satisfy cuisine constraints.
- The last day has no lodging (`"-"`). Every other night needs lodging in the city where you sleep that night.
