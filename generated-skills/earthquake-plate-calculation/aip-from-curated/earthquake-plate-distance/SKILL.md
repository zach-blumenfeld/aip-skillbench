---
name: earthquake-plate-distance
description: Find the earthquake inside a tectonic plate that lies furthest from (or nearest to) that plate's boundaries, using geopandas with an EPSG:4087 metric projection on USGS earthquake GeoJSON and PB2002 plate/boundary GeoJSON. Use for questions like "which 2024 earthquake in the Pacific plate is furthest from any plate boundary", point-in-plate filtering, point-to-boundary distances in km, and writing the answer (id, place, time, magnitude, coordinates, distance) to a file.
license: MIT
compatibility: Python 3 with geopandas, shapely, pyproj, pandas (the task container pins geopandas 1.0.1, shapely 2.0.6, pyproj 3.7.0).
metadata:
  aip-version: "0.5a1"
  source-skill: geospatial-analysis
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
  Answer "which earthquake in plate X is furthest from / nearest to the plate boundary" from a
  USGS earthquake GeoJSON plus PB2002 plate polygons and boundary lines. A decision fixes the
  direction and which boundaries count; the agent maps the request to file paths, plate and
  filters; one script does the geopandas work the correct way (point-in-polygon with .within(),
  project to EPSG:4087 metres, union the boundary segments once, one vectorised .distance(),
  nlargest/nsmallest); the agent writes the answer in the requested format.

trigger_when:
  - A task asks which earthquake inside a tectonic plate is furthest from, or closest to, a plate boundary.
  - A task gives earthquake data (USGS GeoJSON) with PB2002_plates.json / PB2002_boundaries.json and asks for distances in km.
  - Computing point-to-line distances or point-in-polygon membership between earthquakes and plate geometries.

do_not_use_when:
  - The request is about distances between two earthquakes or to a city, not to plate boundaries.
  - There is no plate polygon/boundary data and the task is pure catalogue statistics (counts, magnitudes over time).

steps:
  - name: classify-request
    kind: decision
    description: Decide the selection direction and which boundary segments the distance is measured to.
    inputs:
      - name: task
        type: string
        description: The full task text, verbatim, including file locations and output requirements.
    questions:
      extreme:
        type: choice
        instructions: Does the request want the earthquake with the largest or the smallest distance to the boundary?
        criteria:
          furthest: Furthest, farthest, most distant, largest distance, deepest into the plate interior.
          nearest: Nearest, closest, smallest distance to the boundary.
      boundary_scope:
        type: choice
        instructions: >
          Which boundaries is the distance measured to? Default to plate whenever the request talks
          about "the plate boundary", "its boundaries" or "the boundary of the X plate", and also when
          it says "any plate boundary" while restricting the earthquakes to plate X (for an earthquake
          inside X the nearest boundary is one of X's own). Choose any only when the request
          explicitly wants every boundary in the file regardless of plate.
        criteria:
          plate: Only segments where the target plate is PlateA or PlateB.
          any: Every boundary segment in the boundaries file.
    thresholds:
      extreme: 0.2
      boundary_scope: 0.4
    inputs_to: frame-request

  - name: frame-request
    kind: client_task
    description: Map the request to absolute input paths, target plate, explicit filters, and the output spec.
    inputs:
      - name: task
        type: string
      - name: extreme
        type: string
      - name: boundary_scope
        type: string
    template: assets/frame_request.md
    references:
      - path: references/pb2002-plate-codes.md
        description: PB2002 code/name table and aliases. Load only if the request names the plate by an alias you cannot map to a Code or PlateName.
    inputs_to: compute-distance

  - name: compute-distance
    kind: execution
    description: >
      Load the three GeoJSON files, resolve the plate, keep earthquakes .within() its polygon,
      project to EPSG:4087, measure distance to the union of the selected boundary segments in km,
      and return the chosen earthquake plus a compact top-5 ranking and stats. Exits non-zero with a
      plain message (missing file, unknown plate with the list of available codes, no earthquakes
      in the plate); fix the input it names and rerun.
    inputs:
      - name: earthquakes_path
        type: string
        description: Absolute path to the USGS earthquake FeatureCollection.
      - name: plates_path
        type: string
        description: Absolute path to PB2002_plates.json (Code, PlateName).
      - name: boundaries_path
        type: string
        description: Absolute path to PB2002_boundaries.json (Name, PlateA, PlateB).
      - name: plate
        type: string
        description: PB2002 code or plate name, e.g. PA or Pacific.
      - name: extreme
        type: string
        description: furthest or nearest.
      - name: boundary_scope
        type: string
        description: plate or any.
      - name: filters
        type: object
        description: Optional min_magnitude, max_magnitude, start_time, end_time (end exclusive), event_type; empty object for none.
      - name: output_path
        type: string
        description: Absolute path the answer must be written to, or "" (not used by the script; carried to write-answer).
      - name: output_spec
        type: string
        description: The request's output requirements verbatim, or "" (not used by the script; carried to write-answer).
    script: scripts/compute_distance.py
    timeout: 300
    inputs_to: write-answer

  - name: write-answer
    kind: client_task
    description: Write the computed result in exactly the requested format and location, then verify the file.
    inputs:
      - name: task
        type: string
      - name: output_path
        type: string
      - name: output_spec
        type: string
      - name: plate_code
        type: string
      - name: plate_name
        type: string
      - name: extreme
        type: string
      - name: boundary_scope
        type: string
      - name: result
        type: object
      - name: ranking
        type: list[*]
      - name: stats
        type: object
      - name: method
        type: string
      - name: warnings
        type: list[*]
    template: assets/write_answer.md
    references:
      - path: references/geopandas-method.md
        description: The same method as a hand-run geopandas snippet with its rules. Load only if the request needs a variant the script cannot produce (e.g. a different output column it lacks) and you must compute it yourself.
    inputs_to: end

  - name: end
    kind: end
    description: The written answer and where it was written.
    inputs:
      - name: answer
        type: object
        description: The answer object exactly as written or reported.
      - name: output_path
        type: string
        description: Path of the written file, or "" when only reported.

anti_patterns:
  - Calculating distances in EPSG:4326 (degrees treated as equal distances everywhere); always project to EPSG:4087 first.
  - Hand-rolling Haversine, point-in-polygon tests, or loops over individual boundary vertices instead of .within(), union_all()/unary_union and one .distance() call.
  - Shifting longitudes by +-360 to "fix" the antimeridian; use the published geometries with geopandas operations.
  - Swapping lat/lon - USGS coordinates and shapely Points are (lon, lat).
  - Measuring to every boundary in the file, or to the plate polygon outline, when the request means the target plate's own boundary segments.
  - Matching boundaries by substring (Name contains "PA") when a whole-token or PlateA/PlateB match is available.
  - Projecting the whole dataset before filtering, or projecting inside a loop.
  - Rounding distance_km or renaming output keys beyond what the request asks; hardcoding an expected earthquake instead of computing it from the given files.
```
