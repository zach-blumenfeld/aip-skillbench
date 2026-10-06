---
name: earthquake-plate-distance
description: Compute distances between earthquakes (USGS GeoJSON) and PB2002 tectonic plate boundaries using geopandas with a metric projection — e.g. "which earthquake inside the Pacific plate is furthest from any Pacific plate boundary". Use when a request mentions earthquakes with plates/boundaries, "nearest/furthest earthquake to a plate boundary", or asks for a distance in km between seismic events and plate edges.
license: MIT
compatibility: Requires Python with geopandas>=1.0, shapely>=2.0, pyproj>=3.7 available where scripts run (the task's container ships these; locally, bootstrap a venv — see source/README.md).
metadata:
  aip-version: "0.5a1"
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
  Answer "earthquake vs. plate boundary" questions over USGS earthquake
  GeoJSON and the PB2002 plates/boundaries dataset. Parse the user's
  request into a target plate, metric, and boundary scope; run a single
  geopandas computation that projects to a metric CRS (EPSG:4087),
  filters earthquakes to the plate, unions the relevant boundaries, and
  measures distances in kilometers; return the headline number (and the
  specific earthquake, when the metric picks one).

trigger_when:
  - A user asks for the earthquake inside a named plate that is
    furthest from, nearest to, or at some aggregate distance from the
    plate's boundaries.
  - A task provides USGS-format earthquake GeoJSON and PB2002
    plates/boundaries GeoJSON and asks a distance question over them.
  - A request names tectonic plates (Pacific, Nazca, North America, …)
    and seismic events together and asks for a km-distance answer.

do_not_use_when:
  - The question is about earthquake magnitude, depth, timing, or
    frequency alone — no plate-boundary distance is needed.
  - The input data is not GeoJSON / not the PB2002 schema and would
    need its own loader (adapt the script in that case, do not force
    the inputs through this skill).
  - The user wants a map or visualization rather than a numeric answer.

steps:
  - name: parse-request
    kind: client_task
    description: >
      Extract plate_code (two-letter PB2002), metric (furthest / nearest /
      mean / median), and boundary_scope (plate / all) from the user's
      free-form request. Keep user_request and the three file paths on
      the state so downstream steps can use them.
    inputs:
      - name: user_request
        type: string
        description: The user's question verbatim.
      - name: earthquakes_path
        type: string
        description: Absolute path to the earthquakes GeoJSON (USGS FeatureCollection).
      - name: plates_path
        type: string
        description: Absolute path to the PB2002 plates GeoJSON.
      - name: boundaries_path
        type: string
        description: Absolute path to the PB2002 boundaries GeoJSON.
    template: assets/parse_request.md
    references:
      - path: references/pb2002-plate-codes.md
        description: Look up a plate's two-letter Code from its name (Pacific→PA, Nazca→NZ, …); also explains why boundary filtering uses PlateA/PlateB, not substring match on Name.
    inputs_to: compute

  - name: compute
    kind: execution
    description: >
      Load the three GeoJSON files, filter earthquakes to those inside
      the target plate polygon (.within), project both earthquakes and
      the plate's boundary segments to EPSG:4087, union the boundaries
      into one geometry, and compute per-earthquake distances in km.
      Return the requested metric (and the picked earthquake for
      furthest/nearest).
    inputs:
      - name: user_request
        type: string
      - name: earthquakes_path
        type: string
      - name: plates_path
        type: string
      - name: boundaries_path
        type: string
      - name: plate_code
        type: string
      - name: metric
        type: string
      - name: boundary_scope
        type: string
    script: scripts/compute_distance.py
    inputs_to: report

  - name: report
    kind: client_task
    description: >
      Turn the computed result into a short answer to the user's original
      question. Lead with the distance in km rounded to two decimals; if
      the metric picked an earthquake, name it by USGS id, magnitude,
      and place. Load references/geopandas-cheatsheet.md if the number
      looks wrong before writing the answer.
    inputs:
      - name: user_request
        type: string
      - name: summary
        type: string
      - name: distance_km
        type: float
      - name: plate_code
        type: string
      - name: plate_name
        type: string
      - name: metric
        type: string
      - name: n_earthquakes_in_plate
        type: integer
      - name: earthquake
        type: object
    template: assets/report.md
    references:
      - path: references/geopandas-cheatsheet.md
        description: Load if the distance number seems off (e.g. absurdly small when it should be hundreds of km) — the common silent failure is a missed EPSG:4087 projection or substring-matched boundaries.
    inputs_to: end

  - name: end
    kind: end
    description: Final answer plus the structured result that produced it.
    inputs:
      - name: answer
        type: string
      - name: distance_km
        type: float
      - name: plate_code
        type: string
      - name: metric
        type: string

anti_patterns:
  - Computing .distance() in EPSG:4326 and reporting the degree value as km.
  - Filtering boundaries by substring on the Name property instead of PlateA/PlateB (matches wrong neighbors).
  - Looping distance per boundary segment instead of unary_union + one .distance() call.
  - Re-implementing haversine or point-in-polygon logic instead of using geopandas.
  - Hardcoding `/root/earthquakes_2024.json` in the script; the path must come from the state so the pack runs on any file given.
```
