---
name: search-restaurants
description: Retrieve restaurants by city from the bundled dataset. Use this skill when recommending places to eat or validating dining options for a destination, including travel-planning itineraries that need real restaurant names, cuisines, costs, or ratings rather than invented ones.
compatibility: Requires Python 3 with pandas installed and access to the bundled restaurants CSV (at /app/data/restaurants/clean_restaurant_2022.csv when mounted, otherwise resolved relative to the skill's scripts/ directory).
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Look up real restaurants for a given city from a bundled CSV dataset so
  the agent recommends or validates dining options against ground-truth
  data instead of inventing names, cuisines, costs, or ratings. The
  script returns rows with Name, Average Cost, Cuisines, Aggregate
  Rating, and City for every restaurant matching the requested city
  (case-insensitive, whitespace-trimmed).

trigger_when:
  - User asks for restaurant recommendations in a specific city.
  - Building a travel itinerary that needs concrete dining options for one or more destinations.
  - Validating that a restaurant the agent or user mentioned actually exists in a given city.
  - Comparing dining choices across cities by cost, cuisine, or rating.
  - User provides a destination string like "Austin (TX)" or "New York City" and expects matching restaurants.

do_not_use_when:
  - The user asks about a city not covered by the bundled dataset and accepts that limitation — fall back to general knowledge or another data source.
  - The task needs restaurant detail beyond Name, Average Cost, Cuisines, Aggregate Rating, and City (e.g., menus, hours, reservations) — this dataset does not carry those fields.
  - The user wants restaurants filtered by something other than city (e.g., by cuisine globally) — the script's only filter axis is city.

scope_and_approval: >
  Read-only. The script loads a bundled CSV and returns matching rows; it
  performs no writes, no network calls, and no destructive actions. Safe
  to run without approval checkpoints.

steps:
  - name: resolve-city
    description: >
      Decide which city string to pass to the lookup. If the user supplied
      a clean city name (e.g., "San Francisco"), pass it through. If the
      input is a destination with parenthetical context (e.g.,
      "Austin (TX)" or "Springfield (IL)"), strip the parenthetical
      so the lookup matches the dataset's bare-city values — invoke the
      script with `--annotation` so the parenthetical-stripping variant
      runs. Judgment step — the agent picks the right entry point based
      on how the city is phrased.
    inputs:
      - name: raw-city
        type: string
        description: City string as supplied by the user or upstream step.
    outputs:
      - name: city-query
        type: string
        description: City string ready for the lookup script.
      - name: use-annotation-variant
        type: boolean
        description: True when the input carries parenthetical context that must be stripped before matching.

  - name: lookup
    description: >
      Run the bundled lookup script against the resolved city. Returns
      the matching rows as text (one restaurant per line, columns Name,
      Average Cost, Cuisines, Aggregate Rating, City) or one of two
      well-known sentinel strings — "No restaurant data is available."
      or "There is no restaurant in this city." — that the next step
      interprets.
    script: scripts/search_restaurants.py
    depends_on: [resolve-city]
    inputs:
      - name: city-query
        type: string
      - name: use-annotation-variant
        type: boolean
        nullable: true
    outputs:
      - name: lookup-result
        type: string
        description: >
          Either a formatted table of restaurant rows or one of the two
          sentinel strings. Caller must branch on which.

  - name: interpret-result
    description: >
      Branch on the lookup output. If `lookup-result` equals
      "No restaurant data is available." the bundled dataset failed to
      load — surface this as an environment error, not a "no matches"
      answer, and stop. If it equals "There is no restaurant in this
      city." the dataset has no rows for the requested city — tell the
      user the city is not covered and offer to try a nearby covered
      city or fall back to general knowledge with that caveat. Otherwise
      parse the returned rows and present them to the user (or pass them
      to the next agent step) with the columns intact.
    depends_on: [lookup]
    inputs:
      - name: lookup-result
        type: string
    outputs:
      - name: restaurants
        type: list[object]
        nullable: true
        description: Parsed restaurant rows when the lookup succeeded; otherwise null.
      - name: status
        type: string
        description: One of `ok`, `no-match`, `no-data`.

scenarios:
  - need: User asks "what are some good restaurants in San Francisco for our trip?"
    action: >
      Run `resolve-city` (no parenthetical, pass "San Francisco" through), then
      `python scripts/search_restaurants.py --city "San Francisco"`. Interpret
      the printed rows and present them to the user grouped or sorted as the
      itinerary needs.
    outcome: User receives a list of real San Francisco restaurants with
      cost, cuisine, and rating drawn from the bundled dataset.

  - need: Travel planner step hands off the destination string "Austin (TX)".
    context: >
      The dataset stores cities as bare names like "Austin", so the
      parenthetical must be stripped before lookup or the match will fail.
    action: >
      In `resolve-city` set `use-annotation-variant` true; invoke
      `python scripts/search_restaurants.py --city "Austin (TX)" --annotation`.
    outcome: Lookup matches "Austin" rows in the dataset and returns them.

  - need: User asks for restaurants in a small town the dataset does not cover.
    context: Lookup returns the sentinel "There is no restaurant in this city."
    action: >
      Report to the user that the dataset has no entries for that city.
      Offer to try a nearby covered city or to fall back to general
      knowledge with an explicit caveat.
    outcome: User is not misled into thinking the city has no restaurants
      at all — only that this dataset does not cover it.

anti_patterns:
  - Inventing restaurant names, cuisines, prices, or ratings for a city instead of querying the dataset.
  - Passing a parenthetical-decorated city ("Austin (TX)") to the plain `--city` flag and accepting an empty result as "no restaurants" — use `--annotation` for those.
  - Treating "No restaurant data is available." as "no matches for the city"; it means the dataset failed to load and is an environment error.
  - Filtering returned rows by fields the script does not filter on (cuisine, rating, cost) inside the lookup — filter in the caller after the rows come back.
  - Repeating the same lookup across multiple cities sequentially when a single agent step can fan out — call the script once per city and merge.
```
