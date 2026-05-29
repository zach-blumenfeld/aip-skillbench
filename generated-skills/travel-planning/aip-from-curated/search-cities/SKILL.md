---
name: search-cities
description: Resolve a U.S. state name to the list of cities served by the travel-planning background dataset. Use to validate a state before, or expand destination candidates within, downstream lookups against search-flights, search-restaurants, search-attractions, search-driving-distance, and search-accommodations. Dataset-bound — only cities the script returns are valid downstream inputs.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3 and the travel-planning background dataset mounted at /app/data/background/citySet_with_states.txt (the task harness provides this).
---

```yaml
purpose: >
  Resolve a U.S. state name to the set of cities present in the travel-planning
  background dataset (citySet_with_states.txt). Acts as the gating lookup that
  validates state inputs and enumerates the city candidates the other travel
  search-* skills are allowed to operate on. The dataset, not general knowledge,
  is the source of truth — a city absent from the dataset is not a usable
  destination even if it exists in the real world.

trigger_when:
  - User names a state and asks which cities are available, in-scope, or supported.
  - About to call search-flights, search-restaurants, search-attractions, search-driving-distance, or search-accommodations and need to confirm the destination city is in the dataset for that state.
  - Planning a multi-stop itinerary inside one state and need to enumerate sibling cities to expand candidates.
  - You receive a free-form location string ("somewhere in Texas") and have to translate it into concrete city candidates.
  - You need to validate that a user-supplied state name is recognized at all before proceeding.

do_not_use_when:
  - You already have a concrete city and its state, and downstream skills accept the city directly.
  - The destination is outside the United States — the dataset only covers U.S. states.
  - The lookup needed is anything other than cities-by-state (flights, restaurants, attractions, driving distance, accommodations — call those skills instead).
  - The user supplies only a city name with no state context — this skill keys on state, not city.

scope_and_approval: >
  Read-only. The script reads citySet_with_states.txt and returns either a list
  of cities or one of two literal error strings. No writes, no network, no
  approval gate required.

steps:
  - name: lookup-cities
    description: >
      Run scripts/search_cities.py with the user-supplied state name. Invocation:
      `python scripts/search_cities.py --state "<state>"`. The script trims
      whitespace and matches state names case-insensitively, so pass the state
      through as the user wrote it — do not pre-normalize. Stdout is one city per
      line on success, or a single error line on failure.
    script: scripts/search_cities.py
    inputs:
      - name: state
        type: string
        description: U.S. state name as supplied by the user or upstream skill (any case, surrounding whitespace tolerated).
    outputs:
      - name: lookup-result
        type: string
        description: Raw stdout from the script — either a newline-separated list of cities, the literal "Invalid state.", or the literal "No city data is available."

  - name: interpret-result
    description: >
      Branch on the shape of `lookup-result`. Three distinct cases the script
      can produce, each requiring a different agent response.

      Success — multiple lines, each a city name: parse as `list[string]` and
      hand the list downstream. These are the only cities the other travel
      search-* skills are guaranteed to accept for this state.

      "Invalid state." (exact literal, single line): the state name was not
      recognized in the dataset. Do NOT fall back to general knowledge to
      invent cities. Surface the failure to the user and consider whether
      they typed a misspelling, a city instead of a state, an abbreviation
      (the dataset uses full names like "California", not "CA"), or a
      non-U.S. region. Re-run with a corrected state on confirmation.

      "No city data is available." (exact literal): the dataset file was
      missing or empty when the script ran. Escalate — this is an environment
      fault, not user input. Do not retry the same call; report the broken
      dataset path so the task harness can be inspected.
    inputs:
      - name: lookup-result
        type: string
    outputs:
      - name: cities
        type: list[string]
        description: Parsed list of valid cities for the state. Empty/absent when interpret-result hit either of the two error literals.

scenarios:
  - need: User asks "what cities are in California?"
    action: >
      Run `python scripts/search_cities.py --state "California"`. Parse the
      multi-line stdout into a list. Return the cities verbatim.
    outcome: Caller gets the authoritative dataset list — the only cities the other travel search-* skills will accept for California.

  - need: Planning a trip and the user picks a destination city, "Sedona, Arizona", before flight search.
    context: Need to confirm Sedona is in the dataset before calling search-flights, which would otherwise return nothing useful.
    action: >
      Run `python scripts/search_cities.py --state "Arizona"`. Look for "Sedona"
      in the returned list (case-insensitive comparison is safe). If present,
      proceed to search-flights with "Sedona". If absent, tell the user Sedona
      is not in the travel-planning dataset and offer the in-state cities that
      ARE present (e.g., Flagstaff, Phoenix) as alternatives.
    outcome: Prevents wasted downstream calls and gives the user a recoverable next step rooted in real dataset coverage.

  - need: User types a state by abbreviation — "CA".
    action: >
      First call with `--state "CA"`. Script returns "Invalid state." because
      the dataset keys are full names. Resolve the abbreviation to "California"
      (general knowledge) and re-run with `--state "California"`. Confirm the
      user accepted the expansion if it was ambiguous.
    outcome: Recovers from a common input form without inventing cities or silently dropping the request.

integrations:
  - partner: search-flights / search-restaurants / search-attractions / search-driving-distance / search-accommodations
    body: >
      This skill gates those. They all key on city; if the city is not returned
      by search-cities for its state, those skills will return empty or fail.
      Run search-cities first whenever the destination's dataset presence is
      uncertain.

anti_patterns:
  - Recalling cities-in-state from general world knowledge instead of running the script. Only dataset cities are valid downstream — invented cities will fail in every other search-* skill.
  - Iterating over "Invalid state." or "No city data is available." as if it were a list of cities (it is one string, not a list).
  - Calling the script with a state abbreviation ("CA", "NY") on first try without expanding to the full name — the dataset keys are full state names like "California", "New York".
  - Calling search-cities with a city name instead of a state name. The script keys on state; a city as input always returns "Invalid state.".
  - Re-running the script repeatedly on "No city data is available." — that error means the dataset itself is missing, not that the input was wrong. Escalate instead.
  - Editing scripts/search_cities.py to change the dataset path. /app/data/background/citySet_with_states.txt is what the task harness mounts.
```
