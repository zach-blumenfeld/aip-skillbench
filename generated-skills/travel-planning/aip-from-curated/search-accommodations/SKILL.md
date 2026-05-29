---
name: search-accommodations
description: Lookup accommodations by city from the bundled dataset. Use this skill when you need to recommend places to stay in a given city or filter lodging options before building an itinerary. Returns rows with NAME, price, room type, house_rules, minimum nights, maximum occupancy, and review rate number for the requested city.
compatibility: Requires Python 3.9+ with pandas. The bundled dataset lives at /app/data/accommodations/clean_accommodations_2022.csv inside the task container, with a repo-relative fallback for local runs.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Look up lodging options for a single city from the bundled accommodations
  CSV. Wraps a small pandas helper that resolves the dataset path, cleans the
  rows, and performs a case-insensitive city filter. Use as a building block
  when recommending places to stay or pre-filtering lodging before itinerary
  planning.

trigger_when:
  - User asks where to stay in a specific city.
  - Building or revising an itinerary and lodging needs to be picked.
  - Filtering accommodations by city before applying further criteria
    (price, room type, rating, house rules).
  - User mentions a city alongside hotels, Airbnb, lodging, rooms, or "places
    to stay".

do_not_use_when:
  - The user wants accommodations across multiple cities at once — call this
    skill once per city and combine, or use a broader search skill if one
    exists.
  - The user wants attractions, restaurants, flights, or driving distance —
    those are separate skills in the travel-planning suite.
  - No city has been identified yet. Resolve the city first; this skill takes
    exactly one city string.

scope_and_approval: >
  Read-only. The skill loads a bundled CSV and filters it in memory. No writes,
  no network calls, no approvals required.

steps:
  - name: resolve-city
    description: >
      Determine the single city string to look up. Parse it from the user's
      request, the itinerary state, or upstream skill output. If multiple
      candidates are plausible, disambiguate with the user before calling the
      lookup — the script does an exact (case-insensitive) match against the
      `city` column, so "NYC" will not match "New York" and "Paris, France"
      will not match "Paris".
    outputs:
      - name: city
        type: string
        description: Canonical city name as it appears (or is expected to appear) in the dataset's `city` column.

  - name: lookup-accommodations
    description: >
      Run the bundled lookup. Importable as `Accommodations` from
      `scripts/search_accommodations.py`, or invoke as a CLI
      (`python scripts/search_accommodations.py --city "<city>"`). The script
      resolves the dataset path (container path first, repo fallback second),
      loads the CSV, keeps only the lodging-relevant columns, drops rows with
      missing values, and returns rows whose `city` matches case-insensitively.
    script: scripts/search_accommodations.py
    inputs:
      - name: city
        type: string
    outputs:
      - name: results
        type: object
        description: >
          Either a pandas DataFrame with columns NAME, price, room type,
          house_rules, minimum nights, maximum occupancy, review rate number,
          city — or one of two sentinel strings: "There are no accommodations
          in this city." (no rows match) / "No accommodations data is
          available." (dataset empty or unreadable).

  - name: present-results
    description: >
      Surface the results to the user or the calling step. If `results` is a
      DataFrame, summarise or table-format it for the agent's response; rank or
      filter (price, review rate, room type, house rules) per the user's
      criteria before recommending. If `results` is one of the sentinel
      strings, relay that fact plainly and suggest a nearby or alternative
      city rather than re-running the same query.
    inputs:
      - name: results
        type: object
    outputs:
      - name: recommendation
        type: string
        description: Human-readable lodging recommendation or no-results message.

modes:
  - name: library
    body: >
      Import in Python: `from search_accommodations import Accommodations; acc
      = Accommodations(); acc.run("Seattle")`. Returns a DataFrame on hit,
      string sentinel on miss. Prefer this mode when calling from a notebook
      or composing with other skills in the same Python process.
  - name: cli
    body: >
      Invoke the script directly: `python scripts/search_accommodations.py
      --city "Seattle"`. Prints the table without the pandas index, or prints
      the sentinel string. Use this mode for one-off inspection from a shell.

scenarios:
  - need: User asks "where should I stay in Seattle?" while planning a trip.
    action: >
      resolve-city → "Seattle"; lookup-accommodations → DataFrame; present
      top entries sorted by `review rate number` descending, highlighting
      price and room type.
    outcome: A short recommendation list grounded in the bundled dataset.

  - need: User asks for lodging in "NYC" but the dataset uses "New York".
    context: >
      The script's exact case-insensitive match on the `city` column means
      "NYC" returns the no-results sentinel even though New York rows exist.
    action: >
      Disambiguate before calling the script — confirm "New York" with the
      user (or infer it from itinerary context) and pass that as the `city`
      input.
    outcome: A matching DataFrame instead of a false-negative miss.

  - need: User wants a family-friendly stay in Laredo for 4 nights.
    action: >
      lookup-accommodations with "Laredo"; in present-results, filter the
      returned DataFrame to rows where `minimum nights` ≤ 4 and
      `maximum occupancy` ≥ family size, then check `house_rules` for
      child-friendliness before recommending.
    outcome: Filtered shortlist that respects the user's constraints.

anti_patterns:
  - Passing multiple cities in one call. The script matches exactly one city
    string; loop over cities instead.
  - Treating a no-results sentinel as a DataFrame and trying to iterate or
    index into it. Type-check or string-check before formatting.
  - Hard-coding the dataset path in calling code. The script already resolves
    `/app/data/accommodations/clean_accommodations_2022.csv` (container) or
    the repo-relative fallback; override only via the `path` constructor
    argument when truly needed.
  - Reinventing the filter in raw pandas instead of calling
    `Accommodations.run()`. The helper handles column selection, NaN drop,
    city normalization, and the sentinel strings — duplicating that logic
    drifts.
  - Recommending lodging from the wrong city because the requested city did
    not match the dataset spelling exactly. Resolve the canonical city name
    first.
```
