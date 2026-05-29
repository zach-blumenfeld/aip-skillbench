---
name: search-flights
description: Search flights by origin, destination, and departure date using the bundled flights dataset. Use this skill when proposing flight options or checking whether a route/date combination exists.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.9+ and pandas. The script resolves the bundled flights CSV at /app/data/flights/clean_Flights_2022.csv (container) or <skill>/../../data/flights/clean_Flights_2022.csv (task workspace).
---

```yaml
purpose: >
  Filter the bundled cleaned-flights CSV
  (`/app/data/flights/clean_Flights_2022.csv`) by origin city, destination
  city, and departure date and return the matching flight rows. Backs the
  "do flights exist for this leg / what are they?" decision in a
  multi-city itinerary workflow. The dataset is U.S. domestic flights for
  calendar year 2022 (~380k rows); out-of-year dates or non-U.S. legs will
  not match.

trigger_when:
  - Proposing flight options between two named cities on a specific date.
  - Validating that a flight leg the user proposed actually exists in the
    bundled dataset before recommending it in an itinerary.
  - Pulling price, departure/arrival times, and distance for a known
    route/date so the planner can rank or rollup options.
  - Quoting flight times or distances back to the user (use the dataset,
    not memory — the task explicitly forbids fabricated data).

do_not_use_when:
  - The itinerary explicitly forbids flights (e.g., "no flights, self-driving
    only") — call the driving sibling instead.
  - The leg is non-U.S.-domestic or the date is outside calendar year 2022
    — the dataset will not match and you should say so rather than
    fabricate. Year-2022 U.S. domestic only.
  - Either endpoint is finer than city granularity (airport code, terminal,
    address) — the CSV is keyed on bare city names, not airport codes.
  - The user wants live availability, fare classes, or booking — this is
    a static historical lookup, not a booking API.

scope_and_approval: >
  Read-only over the bundled CSV. No network calls, no writes, no API keys.
  Safe to invoke without confirmation. The script's only side effect is a
  single `Flights API loaded.` line on stdout when the loader runs.

steps:
  - name: parse-request
    description: >
      Extract origin city, destination city, and departure date from the
      user request. Cities must be bare city names matching the CSV's
      `OriginCityName` / `DestCityName` columns verbatim (e.g.,
      `"New York"`, `"Los Angeles"`, `"Newark"`) — strip any trailing
      qualifier like `" (NY)"` or `", New York"` before passing through.
      Date must be ISO `YYYY-MM-DD` (e.g., `"2022-01-15"`); the CSV's
      `FlightDate` column is compared by string equality, so other
      formats silently miss. Year must be 2022.
    outputs:
      - name: origin
        type: string
        description: Bare origin city name matching the CSV's `OriginCityName`.
      - name: destination
        type: string
        description: Bare destination city name matching the CSV's `DestCityName`.
      - name: departure_date
        type: string
        description: Departure date in ISO `YYYY-MM-DD` form, year 2022.

  - name: lookup-flights
    description: >
      Run the bundled script to filter the flights CSV for the requested
      origin, destination, and date. The script (a) resolves the data
      path — preferring `/app/data/flights/clean_Flights_2022.csv`
      (container) and falling back to a path relative to the script;
      (b) loads the CSV, renames any unnamed index column to `Flight
      Number`, projects to `Flight Number, Price, DepTime, ArrTime,
      ActualElapsedTime, FlightDate, OriginCityName, DestCityName,
      Distance`, and drops rows with NaN in those columns;
      (c) filters by exact match on origin / destination / date. CLI
      form: `python scripts/search_flights.py --origin "<city>"
      --destination "<city>" --date "<YYYY-MM-DD>"` (matching rows
      printed without the pandas index). Python form: `from
      search_flights import Flights; Flights().run(origin, destination,
      date)`. `Flights()` reads and parses the CSV on construction and
      prints `Flights API loaded.` — build one instance per session and
      reuse it across legs; do not reconstruct inside a per-leg loop.
      Use `Flights().run_for_annotation(...)` (or strip the
      parenthetical yourself) when the input city carries a `" (XX)"`
      qualifier. Pass `--path` (CLI) or `path=` (Python) to override the
      data file location when running outside the task container.
    script: scripts/search_flights.py
    inputs:
      - name: origin
        type: string
      - name: destination
        type: string
      - name: departure_date
        type: string
      - name: path
        type: string
        nullable: true
        description: >
          Optional override of the data file location. Omit to use
          `/app/data/flights/clean_Flights_2022.csv` (container) or the
          script-relative fallback.
    outputs:
      - name: result
        type: object
        description: >
          Union return — a pandas `DataFrame` with the columns
          `Flight Number, Price, DepTime, ArrTime, ActualElapsedTime,
          FlightDate, OriginCityName, DestCityName, Distance` (one row
          per matching flight, index reset) on a match, or one of two
          sentinel strings: `"No flight data is available."` (dataset
          empty or unreadable) or
          `"There is no flight from {origin} to {destination} on
          {departure_date}."` (no match for the requested
          origin/destination/date).

  - name: interpret-result
    description: >
      Branch on the return type before passing the value downstream.
      `isinstance(result, pandas.DataFrame)` → matching flights exist;
      rank/filter by `Price`, `DepTime`, or `ActualElapsedTime` per the
      planner's preference and surface the chosen row(s) in the
      itinerary.
      `result.startswith("There is no flight")` → no match for that
      leg/date; tell the user explicitly that the dataset has no flight
      for this triple, suggest checking the city spelling (must match
      the CSV verbatim — see `search-cities` for the canonical names),
      trying an adjacent date in 2022, or substituting a nearby
      well-known city. Do not fabricate a flight to fill the gap.
      `result == "No flight data is available."` → the data file was
      empty or unreadable; surface a hard error rather than silently
      proceeding, because the itinerary cannot be grounded without it.
    depends_on:
      - lookup-flights
    inputs:
      - name: result
        type: object
    one_of:
      - Surface the matching DataFrame rows to the planner
      - Report "no flight on this leg/date" and propose alternatives
      - Surface a missing-dataset hard error (empty/unreadable)

modes:
  - name: cli
    body: >
      Default. Invoke the script as a CLI:
      `python scripts/search_flights.py --origin "New York" --destination "Los Angeles" --date "2022-01-15"`.
      Matching rows are printed without the pandas index, one row per
      flight; sentinel strings are printed as-is. Pass `--path <csv>`
      only to override the default CSV location.
  - name: library
    body: >
      Import the underlying class for batch lookups across many legs:
      `from scripts.search_flights import Flights; f = Flights(); f.run(origin, dest, date)`.
      Prefer this when proposing flights for several legs in one agent
      turn — `Flights()` reloads the CSV on construction (and prints
      `Flights API loaded.`), so a single shared instance avoids the
      repeated load cost. Use `f.run_for_annotation(origin, dest, date)`
      to strip a trailing parenthetical from the city inputs before
      filtering. Inspect `f.get_city_set()` to enumerate every
      origin/destination city in the dataset (useful for spell-checking
      a user-supplied city name).

scenarios:
  - need: "Are there any flights from New York to Los Angeles on January 15, 2022?"
    context: User is sketching a transcontinental itinerary leg and needs to know whether the route is even available before pricing it.
    action: >
      Run
      `python scripts/search_flights.py -o "New York" -d "Los Angeles" -t 2022-01-15`
      (or `Flights().run("New York", "Los Angeles", "2022-01-15")`).
    outcome: >
      A `DataFrame` of every matching flight with columns Flight Number,
      Price, DepTime, ArrTime, ActualElapsedTime, FlightDate,
      OriginCityName, DestCityName, Distance. Rank by Price or DepTime
      and surface the chosen option(s).
  - need: "Is there a flight from Atlantis to Narnia on 2022-03-04?"
    context: User has typed cities that won't appear in the dataset.
    action: >
      Run the script; it returns the sentinel
      `"There is no flight from Atlantis to Narnia on 2022-03-04."`.
    outcome: >
      Tell the user no flight exists for that leg/date in the dataset
      and ask them to confirm the city names (against the canonical set
      via `search-cities`) or pick a different date in 2022. Do not
      fabricate a flight.
  - need: "Plan all five inter-city flights of a 7-day itinerary."
    context: The planner needs many lookups in one turn.
    action: >
      Import `Flights` once, then call `run(...)` per leg:
      `f = Flights(); legs = [f.run(o, d, t) for o, d, t in itinerary]`.
    outcome: >
      The CSV is loaded once (one `Flights API loaded.` line on stdout),
      each leg returns a DataFrame or sentinel, and the planner
      composes the itinerary from the per-leg results.
  - need: "Find a flight on 03/17/2022 from Minneapolis to Cleveland."
    context: User has provided a non-ISO date.
    action: >
      Normalize the date to `"2022-03-17"` before calling the script —
      the `FlightDate` comparison is string-equality, not date-aware,
      so `"03/17/2022"` silently misses.
    outcome: >
      With the normalized ISO date the lookup returns the matching
      flights for that leg; without normalization the agent would
      incorrectly conclude "no flight exists."

anti_patterns:
  - Passing two-letter or qualified city strings (`"NYC"`, `"New York, NY"`, `"Newark (NJ)"`) directly. The CSV is keyed on bare city names with exact-match comparison; qualifiers silently miss. Strip the qualifier, or call `run_for_annotation` which strips a trailing parenthetical for you.
  - Passing a non-ISO date format (`"01/15/2022"`, `"15 Jan 2022"`, `"January 15"`). The `FlightDate` column is ISO `YYYY-MM-DD` and the comparison is string-equality. Normalize to ISO before invoking.
  - Treating the sentinel string `"There is no flight from … on …."` as a flight record. The return type is `DataFrame | str`; check `isinstance(result, pandas.DataFrame)` before iterating rows.
  - Fabricating flight numbers, prices, or times when the lookup misses. The task instruction explicitly forbids data from memory — report "not in dataset" instead.
  - Reconstructing `Flights()` inside a per-leg or per-day loop. The constructor reloads the full ~380k-row CSV every time and prints `Flights API loaded.` to stdout; build one instance per session and reuse.
  - Hard-coding `/app/data/...` outside the task container. The script already falls back to a script-relative path and accepts `--path` (CLI) or `path=` (Python); use the override rather than editing the script.
  - Querying dates outside 2022 or non-U.S.-domestic legs and treating a miss as "no flight available, ever". The dataset is calendar year 2022 U.S. domestic only; out-of-scope queries should be reported as out-of-scope, not as definitive absences.
  - Re-implementing the column projection / NaN-drop / filter logic inline. The bundled script is the source of truth; importing it (or shelling out via the CLI) keeps the column set and matching semantics consistent.
```
