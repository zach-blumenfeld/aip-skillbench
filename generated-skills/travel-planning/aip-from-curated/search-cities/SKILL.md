---
name: search-cities
description: List cities for a given state (or other first-level region) from the bundled travel-planning dataset (`background/citySet_with_states.txt`). Use to validate a state name, expand a state-only destination prompt into candidate cities, or filter a candidate city against the supported universe before invoking sibling travel skills (flights, restaurants, attractions, driving distance, accommodations).
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Map a first-level region name (the dataset calls these "states", but the
  vocabulary covers U.S. states, U.S. territories, and a handful of foreign
  regions — e.g. England, Scotland, Ontario, Tuscany, Wallonia, St. Thomas,
  Saipan) to the list of cities present in the bundled travel-planning
  dataset `background/citySet_with_states.txt`. The dataset is the canonical
  universe of supported origin/destination cities for the sibling travel
  skills (flights, restaurants, attractions, driving distance,
  accommodations); this skill is the gate that decides whether a region has
  any cities at all and which ones a downstream lookup may legitimately use.

trigger_when:
  - User mentions a state or region by name and the agent needs the cities
    available for it before invoking a flight, restaurant, attraction,
    driving-distance, or accommodation lookup.
  - Validating a user-supplied state spelling or normalization before
    another travel lookup ("Did the user mean a real region in the
    dataset?").
  - Expanding a destination prompt that names only a state ("plan a trip in
    California") into the candidate cities to consider.
  - Filtering a candidate city against the supported set — a city is
    supported iff it appears in the list returned for its state.

do_not_use_when:
  - Looking up information about a specific named city — the sibling
    skills (search-flights, search-restaurants, search-attractions,
    search-driving-distance, search-accommodations) take a city directly
    and do not need this lookup.
  - The user supplies a two-letter state abbreviation ("CA", "NY"). The
    dataset is keyed by full region name; codes will miss. Expand the code
    to the full name first, then call this skill.

scope_and_approval: >
  Read-only. The script loads one tab-separated text file from disk and
  returns the city list for a region. No mutations, no network, no external
  services, no dependencies beyond the Python standard library.

steps:
  - name: lookup-cities-for-state
    description: >
      Run the bundled script for the target region. The script (a) resolves
      the data path — preferring `/app/data/background/citySet_with_states.txt`
      (the task container layout) and falling back to a path relative to the
      script; (b) loads the tab-separated `city\tstate` mapping, skipping
      blank lines and malformed rows that lack a tab; (c) returns the cities
      for the requested region. Matching is case-insensitive on the region
      name and the script strips surrounding whitespace, so `"California"`,
      `"california"`, and `" CALIFORNIA "` all match. CLI form:
      `python scripts/search_cities.py --state "<region>"` (one city per
      line on stdout). Python form: `from search_cities import Cities;
      Cities().run("<region>")`. `Cities()` reads and parses the file on
      construction and prints `Cities loaded.` — build one instance per
      session and reuse it, do not reconstruct inside a hot path. Pass
      `--path` (CLI) or `path=` (Python) to override the data file location
      when running outside the task container.
    script: scripts/search_cities.py
    inputs:
      - name: state
        type: string
        description: >
          Full region name as it appears in the dataset's second column.
          Case- and surrounding-whitespace-insensitive. Not a two-letter
          code.
      - name: path
        type: string
        nullable: true
        description: >
          Optional override of the data file location. Omit to use
          `/app/data/background/citySet_with_states.txt` (container) or the
          script-relative fallback.
    outputs:
      - name: result
        type: object
        description: >
          Union return — `list[str]` of city names on a match, or one of
          two sentinel strings: `"Invalid state."` (region not in the
          dataset) or `"No city data is available."` (dataset empty or
          unreadable). Cities are returned in dataset order (first
          appearance in the file), not alphabetised, and retain the
          dataset's original casing.

  - name: interpret-result
    description: >
      Branch on the return type before passing the value downstream.
      `isinstance(result, list)` → the region is supported; use the cities
      as the candidate set for sibling skills.
      `result == "Invalid state."` → the region is not in the dataset
      (typos, two-letter codes, non-supported foreign regions); re-prompt
      for a valid region or fall back to the un-validated state per the
      caller's policy — do not iterate the string as if it were a city
      list.
      `result == "No city data is available."` → the data file was empty
      or missing; surface a hard error rather than silently proceeding,
      because every downstream travel skill depends on this dataset.
    depends_on:
      - lookup-cities-for-state
    inputs:
      - name: result
        type: object
    one_of:
      - Use the returned city list as the supported candidates
      - Re-prompt the user for a valid region (no match)
      - Surface a missing-dataset hard error (empty/unreadable)

scenarios:
  - need: List the cities available in California.
    action: >
      `python scripts/search_cities.py --state California` (CLI) or
      `Cities().run("California")` (Python).
    outcome: >
      A `list[str]` including `"San Diego"`, `"Redding"`, ... in dataset
      order (not alphabetised). The CLI prints one city per line.
  - need: Validate that a user-supplied region name is in the dataset.
    action: >
      Call `Cities().run(user_region)` and branch on
      `isinstance(result, list)`.
    outcome: >
      `True` → region is valid, use the list; `False` and
      `result == "Invalid state."` → region is not in the dataset, ask the
      user to clarify or expand a two-letter code first.
  - need: Decide whether a candidate city is supported by the wider
      travel-planning dataset.
    context: >
      The dataset is the union of all supported cities, partitioned by
      region. Membership in the list returned for a region is the
      definition of "supported".
    action: >
      Look up the cities for the candidate city's region with
      `Cities().run(region)`, then check membership of the candidate
      (case-insensitive comparison on the city name).
    outcome: >
      Supported iff the candidate appears in the returned list.
  - need: Plan a trip in Scotland.
    context: >
      The dataset is not U.S.-only — it includes `England`, `Scotland`,
      `Ontario`, `Tuscany`, `Wallonia`, `Alexandria Governorate`, plus
      Caribbean/Pacific territories like `St. Thomas`, `Saipan`,
      `San Juan`. Do not reject foreign region names without consulting
      the dataset.
    action: >
      `Cities().run("Scotland")`.
    outcome: >
      A `list[str]` of the Scottish cities in the dataset, suitable as the
      candidate set for downstream sibling skills.

anti_patterns:
  - Treating the sentinel string `"Invalid state."` as a one-element city
    list. The return type is `list[str] | str`; check
    `isinstance(result, list)` before iterating.
  - Passing two-letter state codes (`"CA"`, `"NY"`). The dataset is keyed
    by full region name; codes silently miss and yield `"Invalid state."`.
    Expand to the full name first.
  - Assuming the dataset is U.S.-only and refusing foreign regions on
    that basis. The dataset includes U.K., Canadian, Italian, Belgian,
    and Caribbean entries; consult the dataset before rejecting.
  - Re-implementing the parse loop inline. The bundled script already
    handles blank lines, malformed rows that lack a tab, surrounding
    whitespace, and case-insensitive region matching — importing it (or
    shelling out via the CLI) is the source of truth.
  - Reconstructing `Cities()` inside a per-city or per-state loop. The
    constructor re-reads and re-parses the file every time and prints
    `Cities loaded.` to stdout; build one instance per session and
    reuse it.
  - Assuming the returned cities are alphabetised. They are returned in
    dataset order (first appearance in the file). Sort downstream if a
    stable display order matters.
  - Hard-coding `/app/data/...` outside the task container. The script
    already falls back to a script-relative path and accepts `--path`
    (CLI) or `path=` (Python) — use the override rather than editing
    the script.
```
