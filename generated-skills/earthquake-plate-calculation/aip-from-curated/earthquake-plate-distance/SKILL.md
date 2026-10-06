---
name: earthquake-plate-distance
description: Answer earthquake-vs-tectonic-plate distance questions over the PB2002 plate model and a corresponding earthquake GeoJSON/JSON file — find the earthquake inside a named plate that is furthest from (or closest to) that plate's boundary, in kilometres, with correct equidistant-metric-CRS projection. Use when the user asks for the most-interior, deepest-inside, nearest-to-boundary, or furthest-from-boundary earthquake within a specific tectonic plate (Pacific, Nazca, North American, etc.), or any point-to-plate-boundary distance ranking over the PB2002 dataset. Covers plate-code lookup, EPSG:4087 projection, `.within()` membership, boundary filtering, and top-N ranking.
compatibility: Requires Python 3.10+ with geopandas (>=0.14, works with 1.0.x), shapely, pyproj. GeoJSON files for PB2002 plates and boundaries plus an earthquake file (GeoJSON FeatureCollection or JSON array of records with latitude/longitude) must be reachable on disk.
license: MIT
metadata:
  aip-version: "0.5a1"
  author: aip-skillbench
  version: "1.0"
---

# AIP runtime — format 0.5a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the JSON object a step receives. Each step declares its required keys as `inputs`; extra keys pass through.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the final state's shape.

## Execution

The state is one JSON object. It starts as the start step's `inputs` and flows along `inputs_to`; each step's output is merged over it, so keys accumulate and extra keys pass through untouched. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. You may change the state before any step runs; you have the final say at every step.

- **`execution`**: run `script` with one JSON object on stdin, `{"currentState": <state>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout; merge it over the state.
- **`decision`**: answer each question against the state. Each answer collapses to one value under its question name and is merged over the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the state, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the next step's `inputs`; merge them over the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. That state is the procedure's result.

```yaml
purpose: >
  Answer "which earthquake inside plate X is furthest from (or closest to) its
  boundary" questions over the PB2002 plate model and a corresponding
  earthquake file. The client extracts the target plate code and the extremum
  from the user's request; a single geopandas script loads the three GeoJSON/
  JSON inputs, filters the plate, spatially filters the earthquakes with
  `.within()`, projects to the equidistant metric CRS EPSG:4087, computes
  per-earthquake distance to the plate's boundary in kilometres, and returns
  the top-N; the client writes the natural-language answer.

trigger_when:
  - The user asks for the earthquake inside a named tectonic plate that is
    furthest from, or closest to, that plate's boundary.
  - The user asks for a top-N ranking of earthquakes by distance to a plate
    boundary over the PB2002 dataset.
  - The user's task carries three files along the lines of `PB2002_plates`,
    `PB2002_boundaries`, and an earthquakes JSON/GeoJSON, and asks a
    distance-ranking question over them.

do_not_use_when:
  - The question is about earthquake magnitude, depth, timing, or clustering
    rather than distance to a plate boundary.
  - The input data is not the PB2002 plate model or a close analogue (no
    polygon layer of plates and no line layer of boundaries).
  - The question is about distances between arbitrary geographic points with
    no plate involved — a plain geopandas distance call suffices.

steps:
  - name: parse-request
    kind: client_task
    description: Extract the PB2002 plate code, extremum, and top-N from the user's natural-language request.
    inputs:
      - name: request
        type: string
        description: The user's natural-language question, verbatim.
      - name: plates_path
        type: string
        description: Filesystem path to the PB2002 plates GeoJSON (polygons, EPSG:4326).
      - name: boundaries_path
        type: string
        description: Filesystem path to the PB2002 boundaries GeoJSON (lines, EPSG:4326).
      - name: earthquakes_path
        type: string
        description: Filesystem path to the earthquakes file (GeoJSON FeatureCollection or JSON array of records with latitude/longitude).
    template: assets/parse_request.md
    inputs_to: compute

  - name: compute
    kind: execution
    description: Load the three files, spatial-filter earthquakes inside the plate, project to EPSG:4087, compute distance to the plate's boundary in km, and return the top-N.
    inputs:
      - name: plates_path
        type: string
      - name: boundaries_path
        type: string
      - name: earthquakes_path
        type: string
      - name: plate_code
        type: string
        description: Two-letter PB2002 plate code (e.g. "PA", "NA", "NZ"). The script also accepts a plate name as a case-insensitive substring fallback.
      - name: extremum
        type: string
        description: Either "furthest" or "closest". Anything else is coerced to "furthest".
      - name: top_n
        type: integer
        description: How many earthquakes to return, ranked by `distance_km`.
    script: scripts/compute_earthquake_plate_distance.py
    inputs_to: report

  - name: report
    kind: client_task
    description: Turn the numeric top-N into a short natural-language answer to the user's original request.
    inputs:
      - name: request
        type: string
      - name: plate_code
        type: string
      - name: extremum
        type: string
      - name: top_n
        type: integer
      - name: count_in_plate
        type: integer
        description: Number of earthquakes that fell inside the plate polygon via `.within()`.
      - name: top_results
        type: list[*]
        description: Ranked list of earthquake records with `distance_km`, `latitude`, `longitude`, and whatever identifying fields the input carried (e.g. id, place, magnitude, time).
    template: assets/report.md
    references:
      - path: references/geopandas-cheatsheet.md
        description: Load if the pipeline output looks surprising (unexpectedly empty `top_results`, missing identifier fields, a plate-code lookup error) and you need to explain or decide whether to retry with different parameters.
    inputs_to: end

  - name: end
    kind: end
    description: The user-facing answer, the ranked top-N records, and the counts that back them.
    inputs:
      - name: summary
        type: string
      - name: top_results
        type: list[*]
      - name: count_in_plate
        type: integer
      - name: plate_code
        type: string

anti_patterns:
  - Calculating distance directly in EPSG:4326 — degrees are not metres, and the ranking will be wrong at any latitude far from the equator. Always project to EPSG:4087 (or another equidistant metric CRS) first.
  - Hand-rolling a Haversine formula or iterating over boundary vertices instead of calling `.distance()` on a `union_all()` geometry.
  - Checking plate membership by comparing lat/lon ranges instead of `.within()` on the plate polygon.
  - Projecting the entire earthquake catalogue before filtering it down to the plate — filter first, project second.
  - Fabricating earthquake identifiers in the final summary when the input records do not carry them.
```
