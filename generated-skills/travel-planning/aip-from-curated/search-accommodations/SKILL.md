---
name: search-accommodations
description: Retrieve accommodations for a given city from the bundled travel-planning dataset (`accommodations/clean_accommodations_2022.csv`). Use when recommending places to stay, validating that a destination has any lodging at all, or shortlisting candidates before filtering by price, room type, occupancy, house rules, or review score. Returns NAME, price, room type, house_rules, minimum nights, maximum occupancy, review rate number, and city. Sibling skill to `search-cities`, `search-flights`, `search-driving-distance`, `search-restaurants`, `search-attractions`.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Map a city name to the accommodations present in the bundled
  travel-planning dataset (`accommodations/clean_accommodations_2022.csv`).
  The dataset projects each row to eight columns — `NAME`, `price`,
  `room type`, `house_rules`, `minimum nights`, `maximum occupancy`,
  `review rate number`, `city` — and is the canonical source of lodging
  options for the travel-planning task family. This skill is the lookup
  step that turns a chosen destination city into a candidate
  accommodation list; ranking, filtering by price/room-type/occupancy/
  rating, and itinerary slotting happen downstream.

trigger_when:
  - User asks for accommodations, hotels, lodging, or places to stay in
    a specific city.
  - Building a travel itinerary that needs a per-city lodging slot and
    the agent must pull the candidate accommodation set first.
  - Validating that a destination city has any lodging at all before
    committing to it (empty result → reconsider the city).
  - Filtering or ranking accommodations by price, room type, minimum-
    nights compatibility with the trip length, maximum occupancy vs
    party size, house-rules constraints, or review score — pull the full
    city set with this skill first, then sort or filter in pandas
    downstream.
  - Cross-checking whether a user-named property exists in the dataset
    by pulling its city's list and looking the name up.

do_not_use_when:
  - The user has not yet chosen a destination city. Use `search-cities`
    first to expand a state-only prompt into candidate cities.
  - Looking up availability across many cities at once — this skill is
    keyed by a single city per call. Pull the per-city result and
    aggregate downstream rather than calling in a tight loop.
  - The runtime does not have `pandas` installed. The script imports
    pandas at module load and will fail with `ImportError` before any
    lookup runs.
  - The user needs live booking, real-time availability, or pricing for
    dates. The dataset is a static 2022 snapshot — sentinel values, not
    a reservation system.

scope_and_approval: >
  Read-only. The script loads one CSV from disk (pandas) and returns a
  filtered DataFrame for the requested city. No mutations, no network,
  no external services, no booking actions. Requires `pandas` in the
  runtime environment (the original SKILL.md notes `pip install pandas`);
  the bundled data file is expected at
  `/app/data/accommodations/clean_accommodations_2022.csv` inside the
  task container, with a script-relative fallback (`../../data/...` from
  the script) for local runs and a `--path` / `path=` override for any
  other layout.

steps:
  - name: lookup-accommodations-for-city
    description: >
      Run the bundled script for the target city. The script (a) resolves
      the data path — preferring
      `/app/data/accommodations/clean_accommodations_2022.csv` (the task
      container layout) and falling back to a path relative to the
      script; (b) reads the CSV with pandas, projects to the eight
      columns `NAME`, `price`, `room type`, `house_rules`,
      `minimum nights`, `maximum occupancy`, `review rate number`,
      `city`, drops rows with any null in that projection, and strips
      surrounding whitespace from the `city` column; (c) returns the
      rows whose `city` matches the requested city. Matching is
      case-insensitive on the city name (the script lowercases for the
      comparison only — the returned `city` column keeps the dataset's
      original casing). CLI form:
      `python scripts/search_accommodations.py --city "<city>"` (prints
      the DataFrame without the pandas index). Python form:
      `from search_accommodations import Accommodations;
      Accommodations().run("<city>")`. `Accommodations()` reads and
      parses the CSV on construction and prints `Accommodations loaded.`
      to stdout — build one instance per session and reuse it; do not
      reconstruct inside a per-city loop. Constructor knobs: `path=` to
      override the data file location, `city_normalizer=` to pass a
      `Callable[[str], str]` that pre-processes incoming city strings
      (e.g., strip parenthetical region tags) before the case-insensitive
      match.
    script: scripts/search_accommodations.py
    inputs:
      - name: city
        type: string
        description: >
          City name as it appears in the dataset's `city` column.
          Case- and surrounding-whitespace-insensitive. Bare city name —
          no state suffix, no parenthetical (supply a `city_normalizer`
          on the constructor if incoming strings may carry trailing
          tags like `"City (Region)"`).
      - name: path
        type: string
        nullable: true
        description: >
          Optional override of the data file location. Omit to use
          `/app/data/accommodations/clean_accommodations_2022.csv`
          (container) or the script-relative fallback.
      - name: city_normalizer
        type: object
        nullable: true
        description: >
          Optional `Callable[[str], str]` passed to the `Accommodations`
          constructor. Applied to the incoming city string before the
          case-insensitive match. Use to strip parentheticals, expand
          abbreviations, or otherwise normalise caller-supplied city
          names. Identity function by default.
    outputs:
      - name: result
        type: object
        description: >
          Union return — a `pandas.DataFrame` of matching rows with
          columns `NAME`, `price`, `room type`, `house_rules`,
          `minimum nights`, `maximum occupancy`, `review rate number`,
          `city` (fresh `RangeIndex`, no nulls), or one of two sentinel
          strings: `"There are no accommodations in this city."` (city
          not in the dataset) or `"No accommodations data is available."`
          (dataset empty or unreadable). Rows are returned in dataset
          order (first appearance in the CSV), not ranked by price or
          review score.

  - name: interpret-result
    description: >
      Branch on the return type before passing the value downstream.
      `isinstance(result, pandas.DataFrame)` → the city has matching
      accommodations; use the DataFrame for downstream ranking,
      filtering, or itinerary slotting. Treat `price` as a numeric
      column (per-night cost in the dataset's native currency unit) —
      parse with `pandas.to_numeric` if it carries a currency symbol
      or thousands separator; `review rate number` is a 0-5 rating;
      `minimum nights` and `maximum occupancy` are integers that gate
      itinerary fit (drop rows where `minimum nights > trip length` or
      `maximum occupancy < party size`); `house_rules` is freeform text
      and must be string-matched (case-insensitive substring) rather
      than parsed as structured flags. `result == "There are no
      accommodations in this city."` → the city has no entries (typo,
      unsupported city, or a real-but-empty city); reconsider the
      destination, re-prompt the user, or fall back per the caller's
      policy — do not iterate the string as a row list. `result ==
      "No accommodations data is available."` → the data file was
      empty or unreadable; surface a hard error rather than silently
      proceeding, because every downstream lodging recommendation
      depends on this dataset.
    depends_on:
      - lookup-accommodations-for-city
    inputs:
      - name: result
        type: object
    one_of:
      - Use the returned DataFrame as the candidate accommodation set
      - Reconsider the destination city or re-prompt the user (no match)
      - Surface a missing-dataset hard error (empty/unreadable)

modes:
  - name: standard
    body: >
      Pass the city name as supplied (after stripping surrounding
      whitespace). The script handles case-insensitive matching
      internally. Use this for any agent-driven lookup where the city
      string is already a clean place name.
  - name: normalised
    body: >
      Construct `Accommodations(city_normalizer=fn)` when the incoming
      city string may carry annotation tags, abbreviations, or other
      noise the dataset's bare `city` column does not. Common normalizer:
      `lambda c: c.split("(", 1)[0].strip()` to drop trailing
      parentheticals like `"San Francisco (CA)"` before matching.

scenarios:
  - need: List the accommodations available in Seattle.
    action: >
      `python scripts/search_accommodations.py --city "Seattle"`
      (CLI) or `Accommodations().run("Seattle")` (Python).
    outcome: >
      A `pandas.DataFrame` of rows with `NAME`, `price`, `room type`,
      `house_rules`, `minimum nights`, `maximum occupancy`,
      `review rate number`, `city` for every Seattle entry in the
      dataset, in dataset order (not ranked). The CLI prints the frame
      without the pandas index.
  - need: Pick the three cheapest entire-home rentals that fit a party
      of four for a 3-night stay in a given city.
    context: >
      The skill returns the full per-city set unranked; filter and sort
      downstream rather than asking the skill to rank.
    action: >
      `df = Accommodations().run(city);
      df = df[(df["room type"] == "Entire home/apt") &
              (df["maximum occupancy"] >= 4) &
              (df["minimum nights"] <= 3)];
      df["price_num"] = pandas.to_numeric(df["price"], errors="coerce");
      df.nsmallest(3, "price_num")`.
    outcome: >
      Three cheapest entire-home listings whose minimum-nights and
      maximum-occupancy constraints are compatible with the trip. The
      skill itself stays a simple lookup; ranking lives in the caller.
  - need: Validate that a destination city has any lodging at all
      before committing to it.
    action: >
      `result = Accommodations().run(candidate_city)` and check
      `isinstance(result, pandas.DataFrame) and not result.empty`.
    outcome: >
      `True` → keep the city as a destination. `False` and
      `result == "There are no accommodations in this city."` →
      re-prompt or pick a different city.
  - need: Find pet-friendly stays in a given city.
    context: >
      `house_rules` is freeform text with inconsistent phrasing; treat
      it as a substring-match column, not structured flags.
    action: >
      `df = Accommodations().run(city);
      df[~df["house_rules"].str.contains("no pets", case=False, na=False)]`.
    outcome: >
      Rows whose `house_rules` text does not contain a pets-prohibited
      clause. Tighten or relax the regex per the caller's policy — the
      column is not normalised.
  - need: Replay an annotated itinerary item whose city is
      `"Seattle (WA)"`.
    context: >
      The parenthetical is annotation metadata, not part of the city
      name. The dataset is keyed by the bare name; the constructor's
      `city_normalizer` hook handles the strip.
    action: >
      `Accommodations(city_normalizer=lambda c: c.split("(", 1)[0].strip())
      .run("Seattle (WA)")`.
    outcome: >
      Equivalent to `run("Seattle")` — the normalizer drops the
      parenthetical before matching.

anti_patterns:
  - Treating the sentinel string `"There are no accommodations in this
    city."` as a one-row result. The return type is `DataFrame | str`;
    check `isinstance(result, pandas.DataFrame)` before iterating rows
    or reading columns.
  - Reconstructing `Accommodations()` inside a per-city or per-call
    loop. The constructor re-reads and re-parses the full CSV every
    time and prints `Accommodations loaded.` to stdout; build one
    instance per session and reuse it across cities.
  - Asking the skill to rank, filter by price band, or impose an
    occupancy cap. The skill returns the unranked per-city set;
    sorting, filtering, and slicing belong in the caller (the DataFrame
    makes that one line of pandas).
  - Assuming rows are sorted by price, review score, or alphabetised on
    `NAME`. They come back in dataset order (first appearance in the
    CSV). Sort downstream if a stable display order matters.
  - Treating `price` as a guaranteed-numeric column. The dataset may
    carry currency symbols or thousands separators in the source CSV;
    coerce with `pandas.to_numeric(..., errors="coerce")` before
    comparison or aggregation, and drop or impute the NaNs that result.
  - Parsing `house_rules` as a structured flag set. The column is
    freeform prose with inconsistent phrasing — match with
    case-insensitive substring or regex, do not split on a delimiter.
  - Ignoring `minimum nights` and `maximum occupancy` when slotting a
    listing into an itinerary. A 7-day stay cannot use a
    `minimum nights = 30` listing; a party of five cannot use a
    `maximum occupancy = 2` listing. Filter before ranking, not after.
  - Passing two-letter region codes, parenthetical region tags, or
    `"City, State"` strings to `run` directly. The dataset is keyed by
    bare city name. Pre-normalise the string or supply a
    `city_normalizer` on the constructor.
  - Hard-coding `/app/data/...` outside the task container. The script
    already falls back to a script-relative path and accepts `--path`
    (CLI) or `path=` (Python) — use the override rather than editing
    the script.
  - Calling the skill to mutate, book, or reserve. It is a read-only
    snapshot lookup; bookings are out of scope and there is no upstream
    reservation system behind the CSV.
```
