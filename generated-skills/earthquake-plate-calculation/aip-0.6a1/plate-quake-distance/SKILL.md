---
name: plate-quake-distance
description: Find the earthquake inside a tectonic plate (e.g. the Pacific plate) that lies furthest from that plate's boundary, using GeoPandas with a metric projection (EPSG:4087), and write it as JSON (id, place, ISO time, magnitude, lat/lon, distance_km). Use for USGS earthquake GeoJSON plus PB2002 plate polygons/boundaries tasks — spatial filtering with .within(), point-to-boundary distances, furthest/nearest event queries.
license: MIT
metadata:
  aip-version: "0.6a1"
---

# AIP runtime — format 0.6a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the one JSON object a run carries. Each step declares the keys it reads as `inputs`; `execution` and `client_task` steps declare the keys they add as `outputs`, and a `decision` adds one key per question.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the procedure's result.

## Execution

The state starts as the start step's `inputs` and flows along `inputs_to`; each step adds its outputs to it. Every key is produced by exactly one step, so keys accumulate and nothing is overwritten. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. A step sees only those keys: give it its declared `inputs` and nothing else from the state. You have the final say at every step.

- **`execution`**: before the first one, check that this machine has everything `requires` names (the interpreter at its minimum version, the packages, the tools); if anything is missing, stop and name all of it. Run `script` from its folder, launched with the step's `command` when it has one and `python <script>` otherwise, with one JSON object on stdin, `{"state": <the step's inputs>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout holding exactly the step's `outputs`; add them to the state. A non-zero exit, or output missing a declared key, fails the step: stop there and report it rather than doing the step by hand.
- **`decision`**: answer each question from the step's inputs, and from the run so far only when the step sets `history: true`. Each answer collapses to one value under its question name and is added to the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the step's inputs, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the step's `outputs`; add them to the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. Those keys are the procedure's result.

```yaml
purpose: >
  Answer "which earthquake within plate X is furthest from X's boundary?" with GeoPandas.
  A script loads the USGS earthquake GeoJSON and the PB2002 plate polygons and boundary
  lines, keeps the events .within() the plate, measures each one's distance to the union of
  the plate's boundary segments in the metric EPSG:4087 projection, and picks the largest;
  a second script writes the answer JSON. Carries the projection rule, the boundary-selection
  rule, and the antimeridian and depth-coordinate traps an unaided agent falls into.

trigger_when:
  - A task asks for the earthquake furthest from (or nearest to) a plate boundary within a given tectonic plate.
  - Earthquake data (USGS GeoJSON) must be filtered to a plate polygon and measured against plate boundary lines (PB2002_plates.json, PB2002_boundaries.json).
  - A task says to compute geographic distances with GeoPandas projections rather than in degrees.

do_not_use_when:
  - The distance wanted is to something other than a plate boundary (cities, coastlines) — the boundary-selection logic does not apply, though the projection rule in references/geopandas-guide.md still does.
  - The task explicitly demands geodesic (great-circle) distances instead of a GeoPandas projection.

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - geopandas>=1.0
    - shapely>=2.0
    - pandas
    - pyproj

steps:
  - name: analyze
    kind: execution
    description: >
      Load the three files, keep earthquakes within the plate polygon (EPSG:4326), project the
      in-plate events and the union of the plate's boundary segments to EPSG:4087, compute
      distance in km, and return the furthest event plus the runners-up.
    inputs:
      - name: earthquakes_path
        type: string
        description: Earthquake GeoJSON FeatureCollection (USGS format; time in epoch ms, coordinates [lon, lat, depth]), e.g. /root/earthquakes_2024.json.
      - name: plates_path
        type: string
        description: Plate polygons GeoJSON with Code and PlateName columns, e.g. /root/PB2002_plates.json.
      - name: boundaries_path
        type: string
        description: Plate boundary LineStrings GeoJSON with Name, PlateA, PlateB columns, e.g. /root/PB2002_boundaries.json.
      - name: plate
        type: string
        description: Target plate as code or name, case-insensitive — "PA" or "Pacific" for the Pacific plate.
      - name: output_path
        type: string
        description: Where the answer JSON goes, e.g. /root/answer.json (read by write-answer, not by this script).
    script: scripts/analyze.py
    assets:
      - assets/config.json
    timeout: 300
    outputs:
      - name: status
        type: string
        description: '"found" when at least one earthquake lies within the plate, else "no_events_in_plate".'
      - name: plate_code
        type: string
        description: Resolved plate code (e.g. PA).
      - name: plate_name
        type: string
        description: Resolved plate name (e.g. Pacific).
      - name: n_earthquakes
        type: integer
        description: Earthquakes with point coordinates loaded.
      - name: n_in_plate
        type: integer
        description: Earthquakes strictly within the plate polygon.
      - name: n_boundary_segments
        type: integer
        description: Boundary segments whose PlateA/PlateB (or Name) involves the plate.
      - name: metric_crs
        type: string
        description: Projection the distances were measured in (EPSG:4087 from assets/config.json).
      - name: proj_version
        type: string
        description: pyproj and PROJ versions that did the projection; EPSG:4087 distances shift slightly between PROJ releases.
      - name: furthest
        type: object
        description: The answer record — id, place, time (YYYY-MM-DDTHH:MM:SSZ UTC, seconds truncated), magnitude, latitude, longitude, distance_km (2 dp); empty when no event is in the plate.
      - name: top_candidates
        type: list[*]
        description: The top five in-plate events by distance, same shape as furthest, for a sanity check.
    inputs_to: by-status

  - name: by-status
    kind: router
    description: Write the answer when an in-plate earthquake exists; otherwise diagnose why none was found.
    branch_on: status
    branches:
      found: write-answer
      no_events_in_plate: diagnose-empty

  - name: write-answer
    kind: execution
    description: Write the furthest record to output_path as JSON with exactly the fields id, place, time, magnitude, latitude, longitude, distance_km.
    inputs:
      - name: furthest
        type: object
      - name: output_path
        type: string
    script: scripts/write_answer.py
    outputs:
      - name: answer_path
        type: string
        description: Absolute path of the written answer file.
      - name: answer
        type: object
        description: The JSON object written.
    inputs_to: end

  - name: diagnose-empty
    kind: client_task
    description: No earthquake fell inside the plate; check for an input mistake before reporting that none qualifies.
    inputs:
      - name: earthquakes_path
        type: string
      - name: plates_path
        type: string
      - name: plate
        type: string
      - name: output_path
        type: string
      - name: plate_code
        type: string
      - name: plate_name
        type: string
      - name: n_earthquakes
        type: integer
      - name: n_in_plate
        type: integer
    template: assets/no-events.md
    references:
      - path: references/geopandas-guide.md
        description: GeoPandas projection, filtering, and pitfalls guide. Load if you suspect a file-format or coordinate problem and need to recompute by hand.
    outputs:
      - name: diagnosis
        type: string
        description: Which case applies (input problem or genuinely no in-plate event) and the evidence.
    inputs_to: end

  - name: end
    kind: end
    description: The plate analysed, how many events fell inside it, and the status; on the found path the answer file has been written.
    inputs:
      - name: status
        type: string
      - name: plate_code
        type: string
      - name: n_in_plate
        type: integer
      - name: furthest
        type: object

anti_patterns:
  - Calculating distances in EPSG:4326 — .distance() returns degrees there. Project to EPSG:4087 first and divide metres by 1000.
  - Measuring to the plate polygon's outline instead of the boundaries file. The Pacific polygon is split at the antimeridian, so its outline has artificial ±180° edges that are not plate boundaries and shrink the distance for events such as Hawaii's.
  - Measuring to every boundary in the file, or to boundaries of other plates. Keep only segments with PlateA or PlateB equal to the plate code (equivalently Name containing it, e.g. "PA-NA", "AU\\PA").
  - Projecting the raw 3-D USGS points as read by gpd.read_file (tagged EPSG:4979). Build 2-D points from longitude/latitude in EPSG:4326.
  - Hand-rolled Haversine, manual point-in-polygon, manual ±360 longitude shifts, or looping over boundary vertices — use .within(), .union_all() and one .distance() call.
  - Filtering to the plate after projecting the whole dataset; filter first, project once, and .copy() the filtered frame before adding columns.
  - Formatting time from local time or with milliseconds; USGS time is epoch ms UTC and the answer wants YYYY-MM-DDTHH:MM:SSZ.
  - Adjusting the script's distance_km to match a calculation made in another environment. EPSG:4087 is spherical in PROJ 9.4 (pyproj 3.7.0 wheels) but ellipsoidal in newer PROJ, so the same event's distance differs by up to ~0.3% (about 10 km at 3,000+ km). Run in the task's container and report what its stack computes; proj_version records which one did.
  - Rounding latitude/longitude or magnitude; only distance_km is rounded (2 dp).
  - Inventing an answer or buffering the plate when no event lies inside it.
```
