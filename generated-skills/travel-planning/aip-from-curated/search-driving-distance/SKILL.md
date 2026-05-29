---
name: search-driving-distance
description: Estimate ground-travel duration, distance, and rough cost between two U.S. cities (driving or taxi) using the bundled Google distance-matrix CSV. Use when comparing ground transport options, validating a self-drive itinerary leg, or sanity-checking an alternative to a search-flights result. Dataset-bound — only origin / destination pairs present in distance.csv return numbers; pairs that take more than a day are deliberately suppressed.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3, pandas, and the travel-planning distance matrix mounted at /app/data/googleDistanceMatrix/distance.csv (the task harness provides this).
---

```yaml
purpose: >
  Resolve a (origin city, destination city, ground-travel mode) triple to a
  duration, a distance, and an approximate cost using the bundled Google
  distance-matrix CSV (distance.csv). Acts as the ground-leg counterpart to
  search-flights inside travel-planning: when an itinerary leg can be driven
  or taxied, this skill prices and times it. The dataset, not general
  knowledge or live mapping APIs, is the source of truth — a pair absent
  from the CSV returns "no valid information" and must not be backfilled
  from real-world distances. Pairs whose driving time exceeds one day are
  deliberately suppressed so the agent does not propose multi-day ground
  legs without explicit user buy-in.

trigger_when:
  - User asks how long it takes to drive, or how far it is, between two specific U.S. cities in the dataset.
  - Building an itinerary leg where ground transport (self-drive or taxi) is plausible and you need a duration/distance/cost to compare against a flight.
  - User pushes back on a flight recommendation ("can I just drive?") and you need numbers to answer.
  - Validating that a self-drive segment of a multi-stop itinerary is feasible inside the trip's time budget.
  - You already have an origin and destination city and need a rough taxi cost to compare with public transit or a rideshare estimate.

do_not_use_when:
  - You only have a state, not a concrete origin and destination city — run search-cities first to get usable city names.
  - The trip is air-only or the leg is clearly inter-continental / trans-oceanic — call search-flights instead.
  - Either endpoint is outside the United States; the bundled CSV only covers U.S. inter-city pairs.
  - You need turn-by-turn directions, live traffic, a route map, or a multi-stop optimization — this skill only returns a single duration / distance / cost summary, not a route.
  - You need a public-transit, walking, cycling, or rideshare-specific quote — only `driving` and `taxi` have a cost formula; other modes echo back without a cost.

scope_and_approval: >
  Read-only. The script reads distance.csv and prints a single human-readable
  summary line (plus a one-line "GoogleDistanceMatrix loaded." banner on
  stdout that the agent should ignore). No writes, no network calls in the
  bundled-CSV path, no approval gate required.

steps:
  - name: lookup-distance-cost
    description: >
      Run scripts/search_driving_distance.py with the user-supplied origin,
      destination, and mode. Invocation:
      `python scripts/search_driving_distance.py --origin "<origin>" --destination "<destination>" --mode "<mode>"`.
      The script strips any trailing "(...)" qualifier from each city name
      before matching (e.g. "Sedona (AZ)" → "Sedona"), so pass the city as
      the user wrote it. City matching against the CSV is case-sensitive and
      exact after that strip — pass canonical capitalization ("New York",
      not "new york"). Mode is matched two ways inside the script: cost is
      applied when the mode string CONTAINS "driving" (covers "driving",
      "self-driving", etc.) or EQUALS "taxi"; any other mode echoes back
      without a cost field. The script also suppresses any row whose
      duration contains "day" — multi-day ground legs are returned as "no
      valid information." Stdout is two lines: a "GoogleDistanceMatrix
      loaded." banner, then the result line.
    script: scripts/search_driving_distance.py
    inputs:
      - name: origin
        type: string
        description: Origin city as the user / upstream skill wrote it; parenthetical qualifiers are stripped internally.
      - name: destination
        type: string
        description: Destination city, same conventions as origin.
      - name: mode
        type: string
        description: >
          Ground-travel mode. Use "driving" (default) for self-drive
          cost = int(km * 0.05), or "taxi" for cost = int(km). Any other
          string is accepted but returns no cost field.
    outputs:
      - name: lookup-result
        type: string
        description: >
          Raw stdout from the script. Last line is either the success format
          `"<mode>, from <origin> to <destination>, duration: <hh mm>, distance: <X km>[, cost: <int>]"`
          or the failure literal
          `"<mode>, from <origin> to <destination>, no valid information."`

  - name: interpret-result
    description: >
      Discard the leading "GoogleDistanceMatrix loaded." banner and branch
      on the shape of the final line.

      Success — line contains "duration:" and "distance:": parse the four /
      five comma-separated fields into an object
      `{mode, origin, destination, duration, distance, cost?}`. `cost` is
      absent when the mode is neither driving-like nor `taxi`. Hand the
      object downstream as the canonical ground-leg estimate.

      Failure — line ends in "no valid information.": one of three things
      happened, distinguishable only by context:
        (a) the (origin, destination) pair isn't in distance.csv,
        (b) the pair IS in the CSV but its duration exceeds one day and
            the script suppressed it,
        (c) the CSV failed to load.
      Do NOT fall back to general world-distance knowledge to invent a
      number. Try, in order: (1) re-run with the cities swapped — the CSV
      stores directional rows and the reverse may exist where the forward
      did not; (2) confirm the cities are dataset cities by calling
      search-cities on each city's state; (3) if both endpoints are
      confirmed dataset cities and both directions still return "no valid
      information.", treat ground transport as infeasible for this leg
      and surface that — recommend search-flights or ask the user to pick
      a closer pair. Do not retry the script on the same arguments
      expecting a different answer.
    inputs:
      - name: lookup-result
        type: string
    outputs:
      - name: leg-estimate
        type: object
        nullable: true
        description: >
          Parsed `{mode, origin, destination, duration, distance, cost?}`
          when the lookup succeeded. Null / absent when the lookup
          returned "no valid information." and no recovery branch
          produced a hit.

scenarios:
  - need: User asks "how long does it take to drive from Seattle to Portland, and roughly what does the gas cost?"
    action: >
      Run `python scripts/search_driving_distance.py --origin "Seattle" --destination "Portland" --mode "driving"`.
      Parse the success line into the leg-estimate object. Report the
      duration verbatim and the cost as a rough self-drive fuel estimate
      (the formula is 0.05 currency-units per km — call that out so the
      user knows it isn't a real fuel-price calculation).
    outcome: User gets a dataset-grounded driving time, a kilometre figure, and a transparent rough-cost number rather than a hallucinated one.

  - need: User is comparing a flight from Detroit to Norfolk against just taking a taxi the whole way.
    context: Flight option already retrieved via search-flights. Need a taxi cost for the same city pair to compare.
    action: >
      Run `python scripts/search_driving_distance.py --origin "Detroit" --destination "Norfolk" --mode "taxi"`.
      The script returns duration, distance, and cost = int(km) (taxi
      formula). Surface the result alongside the flight option so the
      user can compare end-to-end cost and time.
    outcome: User sees that the taxi quote is roughly 1,144 currency-units and ~11 hours vs. a flight, and can make an informed call.

  - need: User asks about driving from St. Louis to Minneapolis but the first lookup returns "no valid information."
    action: >
      The forward row may be missing while the reverse exists. Re-run with
      `--origin "Minneapolis" --destination "St. Louis"`. If that succeeds,
      report it as the symmetric estimate (note the direction was flipped
      because the dataset stores directional rows). If the reverse also
      fails, do NOT invent a number — call search-cities on Missouri and
      Minnesota to confirm both endpoints are dataset cities, then either
      surface the dataset gap to the user or pivot to search-flights.
    outcome: Recoverable lookup failures get a second chance via the reverse direction; genuine gaps are surfaced honestly instead of papered over.

  - need: Itinerary planner is considering driving from Seattle to Miami in one trip.
    action: >
      Run the script with that origin / destination. The CSV row's
      duration almost certainly contains "day", so the script suppresses
      it and returns "no valid information." Do NOT retry. Surface that
      this leg is too long for a single-day drive and steer the user
      toward search-flights or a multi-day driving plan they explicitly
      sign off on.
    outcome: The one-day suppression rule is respected — multi-day ground legs are not silently quoted as if they were normal day-trips.

  - need: User asks for walking time between Boston and Cambridge.
    action: >
      Run with `--mode "walking"`. The script will echo the mode and, if
      the row exists, return duration and distance — but the cost field
      will be absent because the cost formula only fires for driving-like
      and taxi modes. Report duration and distance, and be explicit that
      no cost is available for walking from this skill.
    outcome: Non-priced modes still produce duration / distance when the row exists; the agent does not invent a walking cost from the driving formula.

integrations:
  - partner: search-cities
    body: >
      search-cities gates this skill. If either origin or destination is
      not in the search-cities list for its state, distance.csv will not
      have a row for it and this skill will return "no valid information."
      indefinitely. Run search-cities first whenever the user-supplied
      cities are uncertain.

  - partner: search-flights
    body: >
      Counterpart skill. Use search-driving-distance when the leg is
      plausibly drivable (within a day, both endpoints in CONUS dataset)
      and search-flights otherwise or in parallel for a comparison.
      "no valid information." from this skill, especially when both
      endpoints are confirmed dataset cities, is a strong signal to
      switch to search-flights for that leg.

anti_patterns:
  - Recalling a driving time or distance from general world knowledge when the script returned "no valid information." Only dataset rows are valid; invented numbers will not match what the task expects.
  - Retrying the same `--origin / --destination / --mode` triple after a "no valid information." response. The result is deterministic — retry the REVERSE direction or escalate, do not loop.
  - Treating the "GoogleDistanceMatrix loaded." banner as the result. The result is always the LAST line of stdout; the banner is a load notice the script prints unconditionally.
  - Passing a state name as origin or destination. The script keys on cities, not states; a state name will silently miss every row.
  - Passing a non-driving, non-taxi mode and then quoting a cost. Only modes whose string contains "driving" or equals "taxi" get a cost field — other modes return duration / distance only, by design.
  - Editing the cost formulas (`int(km * 0.05)` for driving, `int(km)` for taxi) to "more realistic" numbers. The formulas are part of the curated skill's contract with the task harness; the task grades against them, not against real fuel or taxi prices.
  - Editing scripts/search_driving_distance.py to change the dataset path. /app/data/googleDistanceMatrix/distance.csv is what the task harness mounts.
  - Reading distance.csv directly from the body of the conversation instead of invoking the script. The script handles parenthesis stripping, distance parsing, the multi-day suppression, and the cost formula — bypassing it loses all four.
```
