---
name: search-flights
description: Search flights by origin city, destination city, and departure date against the bundled 2022 US flights dataset. Use when proposing flight options in a travel itinerary, checking whether a specific route/date pair exists, or pulling per-flight price and timing for budgeting. Returns a pandas DataFrame of matching flights or a "no flight" sentinel string when nothing matches.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Filter the bundled cleaned 2022 US flights CSV
  (`<task-env>/data/flights/clean_Flights_2022.csv`) for an exact match
  on origin city, destination city, and departure date. Returns the
  matching rows (flight number, price, departure/arrival times, elapsed
  time, distance) as a pandas DataFrame, or a human-readable "no flight"
  sentinel string when the route/date combination is not in the dataset.
  The skill answers "what flights exist on this route on this date and
  what do they cost" — it does not pick the best flight, optimize cost,
  or build the itinerary; those decisions belong to the caller.

trigger_when:
  - Building a multi-day itinerary that may include air travel between cities.
  - Checking whether a direct flight from city A to city B exists on a given date.
  - Pulling per-flight price, departure/arrival time, or elapsed time for budget math.
  - Validating that a user-requested route/date pair is feasible before proposing it.

do_not_use_when:
  - The user has ruled out flights (e.g., "no flights, self-driving only") — skip this skill entirely and use `search-driving-distance` instead.
  - The route is international or outside the 2022 US dataset — this skill will return the no-match sentinel and you should fall back to ground transport.
  - You need the cheapest flight across many dates — this skill is a single date lookup; loop over candidate dates in the caller.

scope_and_approval: >
  Read-only against the bundled CSV. No external network calls, no
  writes. Safe to invoke without approval at any point in the planning
  loop.

steps:
  - name: prepare-query
    description: >
      Normalize the origin and destination to bare city names matching
      the dataset (e.g., "Newark", "New Orleans", "Los Angeles"). The
      `OriginCityName` / `DestCityName` columns store plain city names
      with no state suffix and no parenthetical — passing "Newark, NJ"
      or "Newark (NJ)" yields the no-match sentinel even when the route
      exists. Format the date as `YYYY-MM-DD` (string, not a datetime
      object) — the filter is exact string equality against
      `FlightDate`. If the user supplied a city in a richer form, strip
      to the bare name before calling the search; the bundled
      `run_for_annotation` helper does this by truncating at the first
      `(`. When the city name is ambiguous (e.g., "Springfield"), use
      `search-cities` first to pick the right one for the state in scope.
    inputs:
      - name: origin-raw
        type: string
        description: Origin city as supplied by the user or upstream step.
      - name: destination-raw
        type: string
        description: Destination city as supplied by the user or upstream step.
      - name: departure-date-raw
        type: string
        description: Departure date in any user-supplied form.
    outputs:
      - name: origin
        type: string
        description: Bare city name matching `OriginCityName` values in the CSV.
      - name: destination
        type: string
        description: Bare city name matching `DestCityName` values in the CSV.
      - name: departure-date
        type: string
        description: Departure date formatted as `YYYY-MM-DD`.

  - name: search
    description: >
      Run the deterministic exact-match filter on
      (OriginCityName, DestCityName, FlightDate). The script loads the
      CSV once on instantiation, then `Flights.run(origin, destination,
      departure_date)` returns either a `pandas.DataFrame` of matching
      flights with columns `Flight Number, Price, DepTime, ArrTime,
      ActualElapsedTime, FlightDate, OriginCityName, DestCityName,
      Distance`, or the string `"There is no flight from {origin} to
      {destination} on {departure_date}."` when no row matches. Prefer
      importing `Flights` from `scripts/search_flights.py` so you can
      reuse the loaded DataFrame across multiple queries in the same
      session; only fall back to the CLI (`python
      scripts/search_flights.py --origin ... --destination ... --date
      ...`) when import is not available.
    script: scripts/search_flights.py
    depends_on: [prepare-query]
    inputs:
      - name: origin
        type: string
      - name: destination
        type: string
      - name: departure-date
        type: string
    outputs:
      - name: result
        type: object
        description: >
          Either a pandas DataFrame of matching flights, or a "no flight"
          sentinel string. Caller must discriminate with
          `isinstance(result, str)`.

  - name: interpret-result
    description: >
      Branch on the return type. If `isinstance(result, str)` is true,
      treat the route/date as unavailable in the dataset — surface this
      to the planner so it falls back to ground transport or shifts the
      date. If it is a DataFrame, every row is a valid candidate flight:
      `Price` is USD (integer), `DepTime`/`ArrTime` are local 24-hour
      `HH:MM` strings, `ActualElapsedTime` is a free-form duration
      string ("2 hours 33 minutes") not a timedelta, and `Distance` is
      miles. The DataFrame is not pre-sorted — sort by `Price` for
      cheapest, by `DepTime` for earliest. Do not assume non-stop; the
      dataset does not encode connections.
    depends_on: [search]
    inputs:
      - name: result
        type: object
    outputs:
      - name: flights
        type: list[object]
        nullable: true
        description: >
          List of matching flight records when the route/date exists in
          the dataset; null when the sentinel string was returned.

scenarios:
  - need: User asks for flights from New York to Los Angeles on 2022-01-15.
    action: >
      Call `Flights().run("New York", "Los Angeles", "2022-01-15")`.
      The result is a DataFrame; sort by `Price` and present the
      cheapest 1–3 options to the planner.
    outcome: Concrete flight options with prices and times ready for the itinerary.
  - need: User-supplied origin is "Newark (NJ)".
    context: The dataset stores "Newark", not "Newark (NJ)".
    action: >
      Strip the parenthetical before calling — either manually or via
      `Flights().run_for_annotation("Newark (NJ)", ...)`, which trims
      at the first `(`.
    outcome: Exact-match filter succeeds instead of returning the no-flight sentinel.
  - need: User has explicitly said "no flights, self-driving only".
    action: Do not invoke this skill at all; route the planner to `search-driving-distance`.
    outcome: Itinerary respects the user's transport constraint without wasted lookups.
  - need: Planner needs the cheapest flight across a 3-day window.
    action: >
      Loop over each candidate date, call `Flights.run(...)` per date
      (the CSV is loaded once on the first call and reused), drop the
      sentinel responses, concatenate the DataFrames, then sort the
      pooled result by `Price`.
    outcome: Cheapest option across the window without re-loading the CSV per query.

integrations:
  - partner: search-cities
    body: >
      Run `search-cities` first when the user gives only a state or an
      ambiguous city name — it returns the cities present in the
      dataset for that state. Feed a confirmed city name into
      `search-flights` to avoid the no-match sentinel.
  - partner: search-driving-distance
    body: >
      When `search-flights` returns the no-flight sentinel, or when the
      user has ruled out air travel, fall back to
      `search-driving-distance` for the same origin/destination pair to
      keep the itinerary moving.
  - partner: travel-planning caller
    body: >
      The caller owns budget arithmetic, day-by-day sequencing, and the
      final `tool_called` array in the itinerary JSON. This skill only
      surfaces the flight rows; the caller chooses which to include and
      records `"search_flights"` in `tool_called` when it did.

anti_patterns:
  - Passing `"Newark, NJ"` or `"Newark (NJ)"` instead of `"Newark"` — the filter is exact-equality on the bare city name; richer formats silently return the no-flight sentinel.
  - Passing a `datetime.date`/`datetime.datetime` instead of a `YYYY-MM-DD` string — the filter compares string-equality against `FlightDate`.
  - Treating the no-flight sentinel string as an error or empty DataFrame — it is the expected "route not in dataset" signal. Branch on `isinstance(result, str)`.
  - Re-instantiating `Flights()` per query inside a loop — the constructor reads the full CSV every time. Build one instance and reuse `.run(...)`.
  - Using `search-flights` after the user has said "no flights" — wastes a tool call and risks proposing a flight the user already rejected.
  - Assuming the returned DataFrame is sorted — it is not. Sort explicitly by `Price`, `DepTime`, or whichever field the caller actually needs.
  - Assuming non-stop service — the dataset does not encode connections; the row simply asserts a flight exists on that origin/destination/date.
  - Querying dates outside 2022 — the bundled CSV is 2022-only; other years always return the sentinel.
```
