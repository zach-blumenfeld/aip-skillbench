---
name: search-attractions
description: Retrieve attractions by city from the bundled dataset. Use this skill when surfacing points of interest, sightseeing suggestions, things-to-do, landmarks, or tourist sites for a destination city during travel planning, itinerary building, or trip recommendations.
compatibility: Requires Python 3 with pandas installed. Reads the bundled attractions CSV from /app/data/attractions/attractions.csv (container default) or ../../data/attractions/attractions.csv relative to the script.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Look up attractions (points of interest, landmarks, sightseeing spots) for a
  given destination city by querying the bundled attractions CSV. Returns
  structured rows — Name, Latitude, Longitude, Address, Phone, Website, City —
  that downstream steps (itinerary building, recommendations) can ground their
  output on. The dataset is the single source of truth; the skill does not
  invent attractions.

trigger_when:
  - User asks for things to do, sights, landmarks, points of interest, or attractions in a specific city.
  - Building or expanding a travel itinerary and need candidate activities for a destination.
  - Producing destination recommendations or sightseeing suggestions during trip planning.
  - Another travel-planning step needs grounded attraction data (name, address, coordinates, contact) for a city.

do_not_use_when:
  - The request is about restaurants, lodging, transit, or flights — those are out of scope for this dataset.
  - The user wants real-time data (hours, ticket prices, current closures) — the CSV is static and does not carry that information.
  - No destination city has been identified yet; resolve the city first.

scope_and_approval: >
  Read-only. The skill only reads the bundled CSV via `scripts/search_attractions.py`;
  it does not write, mutate, or call external services. Safe to run without
  approval at any point in a planning workflow.

steps:
  - name: resolve-city
    description: >
      Identify the destination city from the user's request or upstream
      itinerary context. Use the common English city name (e.g., "New York",
      "Paris"). Trim surrounding whitespace; do not append country, state, or
      airport codes — the dataset keys on the bare city name.
    outputs:
      - name: city
        type: string
        description: City name to query, as it would appear in the dataset's `City` column.

  - name: query-attractions
    description: >
      Run the bundled lookup script to retrieve all attractions for the
      resolved city. Invoke as `python scripts/search_attractions.py --city "<city>"`.
      The script handles case-insensitive matching, CSV loading, and empty-data
      fallbacks; no other lookup mechanism is needed.
    script: scripts/search_attractions.py
    inputs:
      - name: city
        type: string
    outputs:
      - name: raw-result
        type: string
        description: >
          Either a whitespace-separated table of attraction rows (Name,
          Latitude, Longitude, Address, Phone, Website, City) when matches
          exist, or one of the fixed sentinel strings
          `"There is no attraction in this city."` /
          `"No attractions data is available."` when no rows are returned.

  - name: interpret-results
    description: >
      Inspect `raw-result`. If it is one of the sentinel strings, report the
      empty result to the caller as-is — do NOT fabricate attractions, suggest
      alternates from general knowledge, or guess. If it is a table, parse it
      into a list of attraction records (one per row) and surface only those
      records to downstream steps or to the user.
    inputs:
      - name: raw-result
        type: string
    outputs:
      - name: attractions
        type: list[object]
        description: >
          Zero or more attraction records, each with keys Name, Latitude,
          Longitude, Address, Phone, Website, City. Empty list when the
          dataset has no rows for the city.

scenarios:
  - need: User asks "What are some things to do in New York?"
    action: >
      resolve-city → "New York"; query-attractions →
      `python scripts/search_attractions.py --city "New York"`;
      interpret-results → return the parsed list of NYC attractions.
    outcome: A grounded list of NYC attractions (Name, Address, contact, coords) the agent can summarise or feed into an itinerary.

  - need: Itinerary builder needs sightseeing candidates for a stop in Reykjavik that is not represented in the CSV.
    context: query-attractions returns `"There is no attraction in this city."`.
    action: interpret-results surfaces the empty result; the itinerary step proceeds without attractions for that stop instead of inventing any.
    outcome: Itinerary remains accurate to the dataset; no hallucinated points of interest.

anti_patterns:
  - Inventing or recalling attractions from general knowledge when the script returns no rows or the empty-data sentinel — always defer to the dataset.
  - Passing decorated city names ("New York, NY", "Paris, France", airport codes) to the script — the `City` column holds bare city names and decoration will miss the match.
  - Re-implementing the CSV lookup inline (reading the file directly, calling pandas yourself) instead of invoking `scripts/search_attractions.py` — the bundled script is the source of truth and handles path resolution and column selection.
  - Treating the dataset as authoritative for real-time facts (current hours, prices, closures). It is a static snapshot of name/address/coords/contact.
  - Forgetting that pandas must be installed before the script runs (`pip install pandas`); the script raises on import otherwise.
```
