---
name: search-attractions
description: Retrieve attractions by city from the bundled travel-planning dataset (Name, Latitude, Longitude, Address, Phone, Website, City). Use this skill when surfacing points of interest, building sightseeing suggestions, or populating the `attraction` field of a travel itinerary day — any time the user mentions attractions, sightseeing, things to do, points of interest, or POIs for a specific destination city.
compatibility: Requires Python 3.10+ with pandas installed. Reads `attractions/attractions.csv` from `/app/data` (container) or from `<task>/environment/data/` (local). No network access required.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Query the bundled attractions dataset for points of interest in a given city
  and return them as structured rows the agent can drop into an itinerary. The
  skill is the authoritative source of attraction data for travel-planning
  tasks — agents must not invent attractions from memory.

trigger_when:
  - User asks for attractions, sightseeing, things to do, or points of interest in a specific city.
  - Building or filling the `attraction` field of a travel itinerary day.
  - Composing multi-city travel plans where each day needs at least one POI.
  - Validating that a proposed attraction actually exists in the dataset before naming it in output.

do_not_use_when:
  - The need is for restaurants, accommodations, flights, or driving distances — use the sibling search skills instead.
  - The user is asking general trivia about a landmark unrelated to itinerary planning.
  - No city is identifiable from the request (resolve the city first, then invoke).

scope_and_approval: >
  Read-only. The script reads `attractions.csv` and never writes. Safe to invoke
  without confirmation. No network calls.

steps:
  - name: extract-city
    description: >
      Identify the target city string from the user's request or the itinerary
      day being built. Strip state, country, and qualifiers ("Cleveland, OH" →
      "Cleveland"; "downtown San Diego" → "San Diego"). For multi-city plans,
      pick the city for the day currently being filled.
    outputs:
      - name: city
        type: string
        description: Bare city name to query — no state, no country, no qualifiers.

  - name: query-attractions
    description: >
      Run the bundled CLI against the requested city. Matching is
      case-insensitive and the script handles whitespace; pass the city as
      extracted (do not lowercase or pre-normalize).
    script: scripts/search_attractions.py
    inputs:
      - name: city
        type: string
    outputs:
      - name: results
        type: string
        description: >
          stdout. Either a tab/space-aligned table of attraction rows (columns
          Name, Latitude, Longitude, Address, Phone, Website, City) or one of
          two sentinel strings — "There is no attraction in this city." or
          "No attractions data is available."

  - name: interpret-results
    description: >
      Read the script output. If `results` is the no-attraction sentinel, the
      city is not in the dataset — surface that to the caller and (for
      multi-city itineraries) try a different city rather than fabricating
      attractions. If `results` is the no-data sentinel, the dataset failed to
      load — stop and report the path error. Otherwise treat each non-header
      line as one attraction.
    inputs:
      - name: results
        type: string
    outputs:
      - name: attractions
        type: list[object]
        description: Parsed rows, each with at minimum a `Name` field for itinerary use.

  - name: select-and-format
    description: >
      Pick attractions appropriate to the request (typically 1–3 per day for an
      itinerary). For the travel-planning itinerary output format, join chosen
      `Name` values with semicolons and a trailing semicolon — e.g.,
      `"Rock & Roll Hall of Fame;West Side Market;"`. Preserve exact `Name`
      strings from the dataset; never paraphrase.
    inputs:
      - name: attractions
        type: list[object]
    outputs:
      - name: attraction-field
        type: string
        description: Formatted value ready to drop into a day's `attraction` field.

scenarios:
  - need: Fill the `attraction` field for Day 2 of a Cleveland leg.
    context: >
      Agent has already chosen Cleveland as the day's `current_city`. No prior
      query for this city.
    action: >
      Run `python scripts/search_attractions.py --city "Cleveland"`. Parse the
      stdout table, pick two well-known rows, join their `Name` values with
      `;` and a trailing `;`.
    outcome: >
      `attraction-field` = `"Rock & Roll Hall of Fame;West Side Market;"`,
      ready for the itinerary JSON.

  - need: User asks "what is there to see in San Diego?"
    action: >
      Run `python scripts/search_attractions.py --city "San Diego"`, then list
      the returned `Name` values back to the user with their addresses.
    outcome: >
      Authoritative answer grounded in the dataset, including Cabrillo
      National Monument, La Jolla Shores Park, etc.

  - need: Itinerary requires three Ohio cities but one isn't in the dataset.
    context: >
      `python scripts/search_attractions.py --city "Lima"` returns
      `"There is no attraction in this city."`
    action: >
      Do NOT invent attractions. Tell the planner the city has no entries and
      either swap in a different Ohio city (Cleveland, Cincinnati, Columbus,
      Toledo, Akron, Dayton — confirm by re-querying) or, if the city is
      mandatory, leave `attraction` empty for that day and note the gap.
    outcome: >
      Itinerary stays faithful to the dataset; the no-fabrication rule from
      the parent task is preserved.

  - need: Caller prefers to import the module instead of shelling out.
    action: >
      `from search_attractions import Attractions; print(Attractions().run("New York"))`.
      The class returns a pandas DataFrame on a hit, or the same sentinel
      string on a miss.
    outcome: >
      Same data, programmatic access — useful when post-filtering or joining
      with other skills in the same Python process.

anti_patterns:
  - Inventing attraction names from model memory instead of querying the script. The parent travel-planning task explicitly forbids this.
  - Passing a city with state or country attached (`"Cleveland, OH"`, `"San Diego, CA, USA"`) — the dataset's `City` column is bare city name; matches will silently miss.
  - Lower-casing or title-casing the city before passing it to `--city`. The script does case-insensitive matching itself.
  - Treating the sentinel strings (`"There is no attraction in this city."`, `"No attractions data is available."`) as table rows. They are status messages.
  - Forgetting the trailing `;` when formatting the itinerary `attraction` field — the parent task's output format requires it.
  - Paraphrasing or shortening attraction `Name` values. Use them verbatim from the dataset.
  - Calling this skill for restaurants, lodging, transit, or distances — those have dedicated sibling skills.
```
