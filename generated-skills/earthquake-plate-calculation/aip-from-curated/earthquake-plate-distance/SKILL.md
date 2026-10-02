---
name: earthquake-plate-distance
description: Find the earthquake inside a target tectonic plate that is furthest from that plate's boundaries. Loads USGS earthquake GeoJSON plus PB2002 plate polygons and boundary lines, filters earthquakes by plate polygon, projects to an equidistant metric CRS (EPSG:4087), computes point-to-boundary distances with GeoPandas, and writes the answer JSON (id, place, time, magnitude, latitude, longitude, distance_km). Use when asked to find the most-isolated earthquake within a named plate, when computing earthquake-to-plate-boundary distances, or when doing geospatial point-in-polygon plus distance analysis over plate tectonics data.
license: MIT
compatibility: Requires Python 3 with geopandas, shapely, and pyproj installed (the task container ships geopandas==1.0.1, shapely==2.0.6, pyproj==3.7.0, pandas==2.2.3, numpy==1.26.4). Input files must be readable GeoJSON at the given paths; the output_path directory must be writable.
metadata:
  aip-version: "0.4a0"
---

# AIP runtime — format 0.4a0

You are executing an (Agent Instruction Protocol) AIP procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks using a graph-based workflow. AIP is portable, so while designed for execution with an AIP client and server, you, the agent can play both roles instead. 

## Running

If the `aip` command is available (`aip --help` succeeds), use it: run `aip run <this skill's folder> --input <start.json>` with the start step's inputs as JSON. When the run needs you it prints a JSON pause and exits with code 3. `paused` says why: `decision` — answer the listed questions; `review` — confirm or override the flagged answers; `client_task` — do the task and produce the keys in `expects`. Put your answer in a JSON file and run the `resume` command the pause printed. Repeat until the output has `"done": true`; `state` is the result. If `aip` is not available, execute the procedure yourself, following the semantics below.

Critical terminology:

- **Client**: whoever drives the run: posts each step's input, reviews uncertain decisions, performs client tasks, and makes the final call at every step. As a plain Agent Skill, it is the agent that activated the skill.
- **Server**: runs each step and validates its input against the step's `inputs`. Without one, the activating agent does this itself: runs scripts, answers decision questions by its own judgment, and follows routers.
- **State**: the JSON object a step receives. Each step declares its required keys as `inputs`; extra keys pass through.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to the client, `router` branches on a value in the state, `end` declares the final state's shape.

## Execution

The state is one JSON object. It starts as the start step's `inputs` and flows along `inputs_to`; each step's output is merged over it, so keys accumulate and extra keys pass through untouched. A step runs only if the state holds every key it declares in `inputs`, with the declared types. The client may change the state before any step runs; it has the final say at every step.

- **`execution`**: run `script` with one JSON object on stdin, `{"currentState": <state>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout; it is merged over the state.
- **`decision`**: answer each question against the state. Each answer collapses to one value under its question name and is merged over the state: a noul to `true`/`false`, a choice to its label, a score to its level number. With a decision model, an answer under its threshold is sent to the client to confirm or override before continuing; without one, the client answers the questions.
- **`client_task`**: render `template` with `{key}` from the state, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. The client performs the task, loading `references` if their descriptions apply, and returns the next step's `inputs`; they are merged over the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. That state is the procedure's result.

```yaml
purpose: >
  Given a USGS earthquake GeoJSON, PB2002 plate polygons, and PB2002 boundary
  lines, find the earthquake inside a target plate that is furthest from that
  plate's boundaries. A single script loads the data with GeoPandas, filters
  earthquakes to the target plate polygon in EPSG:4326, projects to the
  EPSG:4087 equidistant-cylindrical metric CRS, unions the target plate's
  boundary segments, computes point-to-boundary distances in kilometres,
  picks the furthest earthquake, converts its Unix-millisecond time to
  ISO 8601 UTC, and writes the answer JSON.

trigger_when:
  - Find the earthquake furthest from a named tectonic plate's boundary while inside that plate.
  - Compute distances from earthquake epicentres to a plate boundary in kilometres using GeoPandas.
  - Perform point-in-polygon filtering of earthquakes by plate polygon and then rank by boundary distance.

do_not_use_when:
  - The task asks for earthquakes outside any specific plate context, or for distances that are not point-to-line/point-to-polygon.
  - Only manual Haversine or great-circle math is allowed — this skill relies on GeoPandas projected distances.
  - The input data is not GeoJSON with a PB2002-style schema (PlateName on plates, Name on boundaries) and cannot be adapted.

steps:
  - name: find-furthest
    kind: execution
    description: >
      Load earthquakes, plate polygons, and boundary lines; keep only
      earthquakes inside the target plate polygon (EPSG:4326 point-in-polygon
      via .within()); project the kept earthquakes and the filtered boundary
      segments to EPSG:4087; union the boundary segments once with
      .unary_union; take .distance() to the union and divide by 1000 for km;
      pick the largest with .nlargest(1, "distance_km"); convert Unix
      milliseconds to ISO 8601 UTC; write the answer JSON (id, place, time,
      magnitude, latitude, longitude, distance_km rounded to 2 decimals) to
      output_path.
    inputs:
      - name: earthquakes_path
        type: string
        description: Absolute path to the USGS earthquakes GeoJSON FeatureCollection.
      - name: plates_path
        type: string
        description: Absolute path to the PB2002 plate polygons GeoJSON (must expose a `PlateName` column).
      - name: boundaries_path
        type: string
        description: Absolute path to the PB2002 boundary lines GeoJSON (must expose a `Name` column encoding the plate pair, e.g. "PA-NA").
      - name: output_path
        type: string
        description: Absolute path to write the answer JSON to (e.g. /root/answer.json).
      - name: plate_name
        type: string
        description: Value to match in the plates layer's `PlateName` column (e.g. "Pacific"). Selects the polygon whose interior earthquakes are considered.
      - name: boundary_name_pattern
        type: string
        description: Substring to match in the boundaries layer's `Name` column so only that plate's boundary segments are kept (e.g. "PA" for the Pacific plate). Use the plate's PB2002 two-letter code.
    script: scripts/find_furthest.py
    inputs_to: end

  - name: end
    kind: end
    description: The path the answer JSON was written to, plus the answer object itself.
    inputs:
      - name: output_path
        type: string
      - name: result
        type: object

anti_patterns:
  - Computing distances directly in EPSG:4326 — degrees are not metres and vary with latitude; always project to a metric CRS such as EPSG:4087 first.
  - Implementing a manual Haversine loop over boundary vertices instead of a single GeoPandas `.distance()` against a unioned boundary geometry.
  - Iterating point-in-polygon checks by hand instead of using `.within()` on the plate polygon.
  - Projecting the full global dataset before filtering — filter first (attribute or spatial), then project the small subset.
  - Skipping `.unary_union` and calling `.distance()` against every boundary segment separately.
  - Manual ±360° longitude adjustments for antimeridian crossings — GeoPandas spatial operations handle it.
  - Rounding the distance before ranking, or picking the answer before rounding to 2 decimals only for the output.
```
