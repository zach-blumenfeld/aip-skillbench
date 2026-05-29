---
name: search-driving-distance
description: Estimate driving/taxi duration, distance, and rough cost between two cities using the bundled distance matrix CSV. Use this skill when comparing ground travel options or validating itinerary legs.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.9+ and pandas. The script resolves the bundled distance matrix CSV at /app/data/googleDistanceMatrix/distance.csv (container) or <skill>/../../data/googleDistanceMatrix/distance.csv (task workspace).
---

```yaml
purpose: >
  Estimate ground-travel duration, distance, and rough cost between two named
  cities for itinerary planning. Backed by a bundled Google Distance Matrix
  CSV (origin, destination, duration, distance) with mode-aware cost rules
  for driving (~$0.05/km) and taxi (~$1.00/km).

trigger_when:
  - Comparing driving versus taxi as a leg of a multi-city itinerary.
  - Validating that a proposed itinerary leg is reachable by ground travel.
  - User asks "how far / how long to drive from X to Y" with city-level granularity.
  - Estimating ground-travel cost for budget rollups.

do_not_use_when:
  - The user needs turn-by-turn directions or live traffic — this is a static lookup.
  - The leg is intercity-air or rail (use the corresponding flight/transit skill instead).
  - Either endpoint is finer than city granularity (street address, neighborhood); the dataset is city-pair only.

scope_and_approval: >
  Read-only over the bundled CSV. No network calls, no writes, no API keys
  required for the default offline path. Safe to invoke without confirmation.

steps:
  - name: parse-request
    description: >
      Extract origin city, destination city, and mode from the user request.
      Mode defaults to "driving"; accept "taxi" when the user asks about a
      cab/taxi/ride-hail leg. Strip any trailing parenthetical (e.g.,
      "Seattle (WA)" → "Seattle") — the CSV uses bare city names.
    outputs:
      - name: origin
        type: string
        description: City name as it should be matched against the CSV's `origin` column.
      - name: destination
        type: string
        description: City name as it should be matched against the CSV's `destination` column.
      - name: mode
        type: string
        description: One of "driving" or "taxi". Drives the cost rule applied downstream.

  - name: lookup-leg
    description: >
      Run the backing script to look up the leg in the bundled distance
      matrix CSV and compute a mode-appropriate cost. The script handles
      CSV resolution, city-name normalization, distance parsing
      ("1,234 km" → 1234.0), and the cost formulas (driving ≈ 0.05·km,
      taxi ≈ 1.00·km). Multi-day driving entries are treated as "no valid
      information" — surface that to the user rather than recommending the leg.
    script: scripts/search_driving_distance.py
    inputs:
      - name: origin
        type: string
      - name: destination
        type: string
      - name: mode
        type: string
    outputs:
      - name: leg-summary
        type: string
        description: >
          Human-readable one-liner of the form
          "{mode}, from {origin} to {destination}, duration: {duration}, distance: {distance}, cost: {cost}"
          — or "...no valid information." when the pair isn't in the CSV or the
          duration is multi-day.

  - name: interpret-result
    description: >
      Read the script's one-liner. If it ends in "no valid information.",
      tell the user the leg isn't in the dataset and suggest checking the
      city spelling, trying the reverse direction (the matrix is mostly
      symmetric but not exhaustively so), or substituting a nearby
      well-known city. Otherwise, report duration / distance / cost back in
      the planner's preferred units and currency context.
    inputs:
      - name: leg-summary
        type: string
    outputs:
      - name: planner-answer
        type: string
        description: Final answer threaded into the itinerary planning conversation.

modes:
  - name: cli
    body: >
      Default. Invoke the script as a CLI:
      `python scripts/search_driving_distance.py --origin "Seattle" --destination "Portland" --mode driving`.
      Pass `--mode taxi` for cab estimates. Pass `--path <csv>` only to override
      the default CSV location.
  - name: library
    body: >
      Import the underlying class for batch lookups across many legs:
      `from scripts.search_driving_distance import GoogleDistanceMatrix; m = GoogleDistanceMatrix(); m.run("Seattle", "Portland", mode="driving")`.
      Prefer this when computing several legs in one agent turn to avoid
      reloading the CSV per call.

scenarios:
  - need: "How long would it take to drive from Seattle to Portland, and roughly what would gas cost?"
    context: User is comparing flying vs driving for a two-city itinerary.
    action: >
      Run `python scripts/search_driving_distance.py -o Seattle -d Portland -m driving`.
      The script returns duration, km, and a driving cost ≈ 0.05·km.
    outcome: >
      Reply with the one-liner the script emits (duration / distance / cost),
      framed as a rough fuel estimate — not an all-in cost.
  - need: "Estimate the taxi fare between Detroit and Norfolk for our cross-country leg."
    context: Planner is rolling up ground-transport costs for a budget.
    action: >
      Run the script with `-m taxi`. The cost formula switches to ≈ 1.00·km.
    outcome: >
      Report the taxi cost figure with a caveat that real taxi/ride-hail prices
      vary widely and the figure is a planning-grade approximation.
  - need: "How far from Atlantis to Narnia?"
    context: User has typed cities that won't appear in any real distance matrix.
    action: >
      Run the script; it returns "...no valid information."
    outcome: >
      Tell the user the leg isn't in the dataset and ask them to confirm the
      city names or pick nearby real cities.

anti_patterns:
  - Re-implementing the cost rules in prose or in a fresh script when scripts/search_driving_distance.py already encodes them — drift between the two will produce conflicting numbers.
  - Passing addresses, neighborhoods, or "<city>, <state>" strings without first stripping the parenthetical/region suffix; the CSV is keyed on bare city names.
  - Treating a multi-day duration as a valid driving leg. The script returns "no valid information." for those on purpose — surface that rather than recommending a 36-hour drive.
  - Quoting the cost figure as a real-world fare. It's a planning-grade approximation (0.05·km for driving, 1.00·km for taxi), not a quote.
  - Calling the Google API path (requires `subscription_key`) when the bundled CSV is sufficient — the offline lookup is the intended default.
```
