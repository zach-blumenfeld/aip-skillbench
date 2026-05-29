---
name: search-restaurants
description: Retrieve restaurants for a given city from the bundled travel-planning dataset (`restaurants/clean_restaurant_2022.csv`). Use when recommending places to eat, validating that a destination has any dining options at all, or expanding a restaurant short-list before ranking by cost, cuisine, or rating. Returns Name, Average Cost, Cuisines, Aggregate Rating, and City. Sibling skill to `search-cities`, `search-flights`, `search-driving-distance`.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Map a city name to the restaurants present in the bundled
  travel-planning dataset (`restaurants/clean_restaurant_2022.csv`). The
  dataset projects each row to five columns — `Name`, `Average Cost`,
  `Cuisines`, `Aggregate Rating`, `City` — and is the canonical source
  of dining options for the travel-planning task family. This skill is
  the lookup step that turns a chosen destination city into a candidate
  restaurant list; ranking, filtering by cuisine/cost/rating, and
  itinerary slotting happen downstream.

trigger_when:
  - User asks for restaurants, places to eat, or dining options for a
    specific city.
  - Building a travel itinerary that needs at least one meal slot per
    city and the agent must pull the candidate restaurant set first.
  - Validating that a destination city has any dining options at all
    before committing to it (empty result → reconsider the city).
  - Filtering or ranking restaurants by cuisine, cost, or aggregate
    rating — pull the full city set with this skill first, then sort or
    filter in pandas downstream.
  - Cross-checking whether a user-named restaurant exists in the
    dataset by pulling its city's list and looking the name up.

do_not_use_when:
  - The user has not yet chosen a destination city. Use `search-cities`
    first to expand a state-only prompt into candidate cities.
  - Looking up cuisine availability across many cities at once — this
    skill is keyed by a single city per call. Pull the per-city result
    and aggregate downstream rather than calling in a tight loop.
  - The runtime does not have `pandas` installed. The script imports
    pandas at module load and will fail with `ImportError` before any
    lookup runs.

scope_and_approval: >
  Read-only. The script loads one CSV from disk (pandas) and returns a
  filtered DataFrame for the requested city. No mutations, no network,
  no external services. Requires `pandas` in the runtime environment
  (the original SKILL.md notes `pip install pandas`); the bundled data
  file is expected at `/app/data/restaurants/clean_restaurant_2022.csv`
  inside the task container, with a script-relative fallback for local
  runs.

steps:
  - name: lookup-restaurants-for-city
    description: >
      Run the bundled script for the target city. The script (a) resolves
      the data path — preferring `/app/data/restaurants/clean_restaurant_2022.csv`
      (the task container layout) and falling back to a path relative to
      the script; (b) reads the CSV with pandas, projects to the five
      columns `Name`, `Average Cost`, `Cuisines`, `Aggregate Rating`,
      `City`, drops rows with any null in that projection, and strips
      surrounding whitespace from the `City` column; (c) returns the
      rows whose `City` matches the requested city. Matching is
      case-insensitive on the city name (script lowercases for the
      comparison only — the returned `City` column keeps the dataset's
      original casing). CLI form:
      `python scripts/search_restaurants.py --city "<city>"` (prints the
      DataFrame without the pandas index). Python form:
      `from search_restaurants import Restaurants;
      Restaurants().run("<city>")`. `Restaurants()` reads and parses the
      CSV on construction and prints `Restaurants loaded.` — build one
      instance per session and reuse it; do not reconstruct inside a
      per-city loop. Pass `--path` (CLI) or `path=` (Python) to override
      the data file location when running outside the task container.
      `Restaurants` also exposes `run_for_annotation(city)` (strips a
      trailing parenthetical before delegating to `run`) and
      `get_city_set()` (returns the set of cities present in the
      dataset, useful as a cheap membership probe).
    script: scripts/search_restaurants.py
    inputs:
      - name: city
        type: string
        description: >
          City name as it appears in the dataset's `City` column.
          Case- and surrounding-whitespace-insensitive. Bare city name —
          no state suffix, no parenthetical (use `run_for_annotation`
          for inputs that may carry `"City (Region)"` trailing tags).
      - name: path
        type: string
        nullable: true
        description: >
          Optional override of the data file location. Omit to use
          `/app/data/restaurants/clean_restaurant_2022.csv` (container)
          or the script-relative fallback.
    outputs:
      - name: result
        type: object
        description: >
          Union return — a `pandas.DataFrame` of matching rows with
          columns `Name`, `Average Cost`, `Cuisines`, `Aggregate Rating`,
          `City` (fresh `RangeIndex`, no nulls), or one of two sentinel
          strings: `"There is no restaurant in this city."` (city not in
          the dataset) or `"No restaurant data is available."` (dataset
          empty or unreadable). Rows are returned in dataset order
          (first appearance in the CSV), not ranked by rating or cost.

  - name: interpret-result
    description: >
      Branch on the return type before passing the value downstream.
      `isinstance(result, pandas.DataFrame)` → the city has matching
      restaurants; use the DataFrame for downstream ranking, filtering,
      or itinerary slotting. Treat `Average Cost` as a numeric column
      (per-person cost in the dataset's native currency unit) and
      `Aggregate Rating` as a 0-5 float; `Cuisines` is a comma-separated
      string and must be split before per-cuisine filtering.
      `result == "There is no restaurant in this city."` → the city has
      no entries (typo, unsupported city, or a real-but-empty city);
      reconsider the destination, re-prompt the user, or fall back per
      the caller's policy — do not iterate the string as a row list.
      `result == "No restaurant data is available."` → the data file
      was empty or unreadable; surface a hard error rather than silently
      proceeding, because every downstream dining recommendation
      depends on this dataset. When you only need to know whether a
      city is supported (not the rows), prefer `Restaurants().get_city_set()`
      and a membership check — it skips the per-call DataFrame filter.
    depends_on:
      - lookup-restaurants-for-city
    inputs:
      - name: result
        type: object
    one_of:
      - Use the returned DataFrame as the candidate restaurant set
      - Reconsider the destination city or re-prompt the user (no match)
      - Surface a missing-dataset hard error (empty/unreadable)

modes:
  - name: standard
    body: >
      Pass the city name as supplied (after stripping surrounding
      whitespace). The script handles case-insensitive matching
      internally. Use this for any agent-driven lookup where the city
      string is already a clean place name.
  - name: annotation
    body: >
      Call `Restaurants().run_for_annotation(city)` when the incoming
      city string may carry a trailing parenthetical region tag
      (`"San Francisco (CA)"`, `"London (UK)"`). The helper strips
      everything from the first `(` onward and trims whitespace before
      delegating to `run`. Useful when the caller is replaying annotated
      itinerary data rather than fresh user input.

scenarios:
  - need: List the restaurants available in San Francisco.
    action: >
      `python scripts/search_restaurants.py --city "San Francisco"`
      (CLI) or `Restaurants().run("San Francisco")` (Python).
    outcome: >
      A `pandas.DataFrame` of rows with `Name`, `Average Cost`,
      `Cuisines`, `Aggregate Rating`, `City` for every San Francisco
      entry in the dataset, in dataset order (not ranked). The CLI
      prints the frame without the pandas index.
  - need: Pick the three top-rated cheap eats for a city.
    context: >
      The skill returns the full per-city set unranked; sort and slice
      downstream rather than asking the skill to rank.
    action: >
      `df = Restaurants().run(city); df = df[df["Average Cost"] <= 30].nlargest(3, "Aggregate Rating")`.
    outcome: >
      Top three restaurants under the cost cap, sorted by aggregate
      rating. The skill itself stays a simple lookup; ranking lives in
      the caller.
  - need: Validate that a destination city has any restaurants at all
      before committing to it.
    action: >
      `result = Restaurants().run(candidate_city)` and check
      `isinstance(result, pandas.DataFrame) and not result.empty`.
    outcome: >
      `True` → keep the city as a destination. `False` and
      `result == "There is no restaurant in this city."` → re-prompt
      or pick a different city.
  - need: Cheap membership probe — is `San Diego` a city in the
      restaurants dataset?
    context: >
      The full per-city filter is unnecessary when the caller only
      wants a yes/no answer. `Restaurants.get_city_set()` returns the
      pre-built set of cities.
    action: >
      `"San Diego" in Restaurants().get_city_set()`.
    outcome: >
      `True` if the city has at least one row in the dataset; `False`
      otherwise. Cheaper than calling `run` and checking the return
      type. Note casing — the set retains the dataset's original
      casing, so normalise both sides if user input may differ.
  - need: Replay an annotated itinerary item whose city is
      `"San Francisco (CA)"`.
    context: >
      The parenthetical is annotation metadata, not part of the city
      name. The dataset is keyed by the bare name.
    action: >
      `Restaurants().run_for_annotation("San Francisco (CA)")`.
    outcome: >
      Equivalent to `run("San Francisco")` — the helper strips the
      parenthetical before matching.

anti_patterns:
  - Treating the sentinel string `"There is no restaurant in this city."`
    as a one-row result. The return type is `DataFrame | str`; check
    `isinstance(result, pandas.DataFrame)` before iterating rows or
    reading columns.
  - Reconstructing `Restaurants()` inside a per-city or per-call loop.
    The constructor re-reads and re-parses the full CSV every time and
    prints `Restaurants loaded.` to stdout; build one instance per
    session and reuse it.
  - Asking the skill to rank, filter by cuisine, or impose a cost cap.
    The skill returns the unranked per-city set; sorting, filtering,
    and slicing belong in the caller (the DataFrame makes that one
    line of pandas).
  - Assuming the rows are sorted by rating, cost, or alphabetised on
    name. They come back in dataset order (first appearance in the
    CSV). Sort downstream if a stable display order matters.
  - Splitting `Cuisines` on comma without trimming. The column is a
    comma-separated string with inconsistent whitespace
    (`"Tea, Pizza, Indian, Seafood"`); split on `, ` or split on `,`
    and strip each item.
  - Passing two-letter region codes, parenthetical region tags, or
    `"City, State"` strings to `run` directly. The dataset is keyed by
    bare city name. Strip parentheticals via `run_for_annotation` or
    pre-normalise the string before the call.
  - Hard-coding `/app/data/...` outside the task container. The script
    already falls back to a script-relative path and accepts `--path`
    (CLI) or `path=` (Python) — use the override rather than editing
    the script.
  - Calling `run` just to test city membership when
    `get_city_set()` would do. Membership checks against the cached
    set are O(1) and skip the per-call DataFrame filter.
```
