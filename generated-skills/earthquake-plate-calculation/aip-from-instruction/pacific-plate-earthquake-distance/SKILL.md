---
name: pacific-plate-earthquake-distance
description: Find the earthquake furthest from the Pacific plate boundary while inside the Pacific plate, given USGS-format earthquakes and the PB2002 plates/boundaries datasets. Use when the task names PB2002 plate data plus a USGS earthquakes JSON and asks for the inland-most quake (max distance to a plate boundary). Handles the Pacific plate's antimeridian crossing by reprojecting to a Pacific-centered Azimuthal Equidistant CRS, computes metric distance with GeoPandas, and writes a JSON answer with id, place, time (ISO 8601), magnitude, latitude, longitude, and distance_km.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.10+ with geopandas, shapely>=2.0, pyproj. Reads/writes local files only; no network needed.
---

```yaml
purpose: >
  Solve "which earthquake is furthest from the Pacific plate boundary, inside
  the Pacific plate?" given a USGS-format earthquakes GeoJSON and the PB2002
  plate-tectonic dataset (boundaries + plates). The skill encodes the
  projection choice (Pacific-centered Azimuthal Equidistant), the Pacific
  plate identifier in PB2002 ("PA"), the USGS field mapping (epoch-ms time,
  `mag` -> `magnitude`), and the antimeridian gotchas that trip up naive
  GeoPandas runs.

trigger_when:
  - User supplies a USGS-format earthquakes JSON plus PB2002 plates and boundaries JSON.
  - Task asks for the earthquake furthest from a plate boundary while inside that same plate (Pacific variant).
  - Required answer schema includes id, place, time (ISO 8601 with Z), magnitude, latitude, longitude, distance_km (km, 2 decimals).
  - Instruction explicitly says to use GeoPandas projections.

do_not_use_when:
  - Plate dataset is not PB2002 (plate codes and column names differ).
  - Distance target is something other than plate boundaries (faults, coasts, trenches as a separate dataset).
  - The "containing plate" is not the Pacific — the projection and code constants here are Pacific-specific.
  - Earthquake catalog is not USGS-style GeoJSON (field names like `mag`, `place`, epoch-ms `time` would not apply).

scope_and_approval: >
  Read-only on inputs. Writes a single JSON file (default /root/answer.json,
  override via --output). No network calls, no destructive operations, no
  approval gate required.

steps:
  - name: verify-inputs
    description: >
      Confirm all three input files exist and are readable: the USGS earthquakes
      GeoJSON, the PB2002 plates polygons GeoJSON, and the PB2002 boundaries
      lines GeoJSON. Standard locations are /root/earthquakes_2024.json,
      /root/PB2002_plates.json, /root/PB2002_boundaries.json. If any file is
      missing, stop and report — do not synthesize substitutes.
    outputs:
      - name: input_paths
        type: object
        description: Resolved paths for earthquakes, plates, boundaries, and output.
  - name: ensure-environment
    description: >
      Ensure geopandas, shapely (>=2.0), and pyproj are importable. The script
      header declares them as PEP 723 inline metadata so `uv run` will resolve
      them automatically; otherwise install with pip before running.
    inputs:
      - name: input_paths
        type: object
    outputs:
      - name: env_ready
        type: boolean
  - name: run-solver
    description: >
      Invoke scripts/solve.py. The script loads the three inputs, filters
      earthquakes to those geometrically within the Pacific plate polygon
      (code 'PA'), reprojects to a Pacific-centered Azimuthal Equidistant CRS
      (+proj=aeqd +lat_0=0 +lon_0=-160) so distances are in metres and the
      antimeridian-spanning Pacific stays contiguous, computes distance from
      each filtered quake to the unioned Pacific boundary geometry (PB2002
      boundaries filtered to PA-adjacent segments; falls back to the polygon's
      own .boundary if attribute filtering fails — equivalent for points
      inside the Pacific), picks the max-distance quake, and writes the
      answer JSON.
    script: scripts/solve.py
    inputs:
      - name: input_paths
        type: object
      - name: env_ready
        type: boolean
    outputs:
      - name: answer
        type: object
        description: The winner record (id, place, time, magnitude, latitude, longitude, distance_km).
      - name: answer_path
        type: string
        description: Path to the written JSON file (default /root/answer.json).
  - name: verify-answer
    description: >
      Read the written JSON and confirm it has all seven required fields with
      the right shapes — `id` (string), `place` (string), `time` (ISO 8601
      string ending in `Z`), `magnitude` (number), `latitude` and `longitude`
      (numbers), `distance_km` (number, 2 decimals). If any field is missing
      or malformed, re-run the solver after diagnosing the cause (usually a
      column-name mismatch in the input data — see references/pb2002-notes.md).
    inputs:
      - name: answer_path
        type: string
    outputs:
      - name: verified
        type: boolean

scenarios:
  - need: USGS 2024 earthquakes GeoJSON plus PB2002 plates/boundaries; identify the inland Pacific quake furthest from the boundary; write /root/answer.json.
    context: Default paths from the task spec; Pacific plate code 'PA' in PB2002.
    action: >
      Run `uv run scripts/solve.py` (or `python scripts/solve.py`) with the
      default arguments. The script handles the within-plate filter, AEQD
      reprojection, and distance computation end-to-end.
    outcome: >
      /root/answer.json populated with id, place, ISO 8601 time, magnitude,
      latitude, longitude, and distance_km rounded to two decimals.

anti_patterns:
  - Computing distance in EPSG:4326 — degrees are not metres; .distance() in geographic CRS returns degrees and is meaningless for this task.
  - Using Web Mercator (EPSG:3857) or any other projection that splits the Pacific at the antimeridian — the Pacific polygon shatters and distances become wildly wrong.
  - Filtering plates by name "Pacific Plate" only — PB2002 typically uses the two-letter code "PA" in the `Code` column, with `PlateName` sometimes empty or formatted differently across distributions. Try the code first.
  - Treating USGS `time` as seconds — USGS feeds are epoch milliseconds. Divide by 1000 before constructing a datetime.
  - Using `mag` directly in the answer — the output schema asks for `magnitude`.
  - Forgetting the km conversion and the 2-decimal rounding on distance_km.
  - Using all PB2002 boundary lines unfiltered in a global projection — projection seams can make distant boundaries appear closer than they are. Either filter to PA-adjacent boundaries (preferred) or use the Pacific polygon's own .boundary.
  - Omitting the `Z` suffix on the ISO 8601 timestamp — the task spec asks for `YYYY-MM-DDTHH:MM:SSZ`.
```
