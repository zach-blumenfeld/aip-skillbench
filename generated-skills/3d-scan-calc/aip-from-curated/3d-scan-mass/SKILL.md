---
name: 3d-scan-mass
description: "Compute the mass of a part from a noisy 3D scan (binary STL) and a Markdown material-density table. Filters debris via largest-connected-component, reads the material ID from the binary STL attribute bytes, looks up its density, converts volume to cm³, and returns mass in grams. Use when a task provides an STL file plus a density/material table and asks for the part's mass, weight, or material."
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
  Given a binary STL scan of a part (possibly contaminated with debris / noise
  triangles) and a Markdown material-density table, compute the mass of the
  main part. The pipeline filters debris by picking the largest connected
  component, reads the material ID from the STL's per-triangle attribute bytes,
  looks up that ID in the density table, converts raw volume to cm³ using the
  caller-supplied coordinate unit, and multiplies to get mass in grams.


  Populate the initial state with three keys (extra keys pass through, so put
  all three in before the first step):
    - stl_path (string): absolute path to the binary STL scan.
    - density_table_path (string): absolute path to the Markdown density table.
      Rows look like `| 42 | Unobtanium | 5.55 | ... |`; the first numeric
      column is the Material ID the STL attribute bytes carry, the third
      column is density in g/cm³.
    - coord_unit (string): unit of STL vertex coordinates. One of
      `cm`, `mm`, `m`, `in`. The STL file does not record units — determine
      this from the task description. A wrong unit scales the answer by 10^3
      or 10^6; if the task is silent, pick the unit that makes the bounding
      box plausible for the described part.

trigger_when:
  - A task provides a binary STL scan plus a density/material lookup table (Markdown or similar) and asks for the part's mass, weight, or material.
  - Scan data is described as noisy, dirty, contaminated, or containing debris, and the main part's mass is wanted.
  - The caller already knows the STL coordinate unit (mm, cm, m, in) and the on-disk paths of both files.

do_not_use_when:
  - The input mesh is not an STL file (e.g. OBJ, PLY, STEP). This pack parses binary STL only, with an ASCII fallback that cannot recover material IDs.
  - The density lookup is not keyed by the integer in the STL attribute bytes (e.g. density is keyed by part name, color, or user prompt).
  - Material IDs are stored outside the STL (sidecar CSV/JSON) rather than in the per-triangle attribute bytes.
  - The task wants per-component masses, surface area, inertia tensor, or any geometric property other than main-part volume → mass.

steps:
  - name: analyze-mesh
    kind: execution
    description: >
      Parse the binary STL at `stl_path`, run connected-component analysis to
      isolate the largest component (the main part, dropping debris / dust /
      noise), and emit its raw volume (in `coord_unit`³) and material ID (from
      the STL attribute bytes of the first triangle in that component).
    inputs:
      - name: stl_path
        type: string
        description: Absolute path to the binary STL file on disk.
    script: scripts/analyze_mesh.py
    inputs_to: compute-mass

  - name: compute-mass
    kind: execution
    description: >
      Parse the Markdown density table at `density_table_path`, convert
      `volume_raw` from (`coord_unit`)³ to cm³ (cm→1, mm→1e-3, m→1e6, in→16.387064),
      look up `material_id` → (material_name, density_g_per_cm3), and compute
      mass_grams = volume_cm3 × density_g_per_cm3. Fail loudly if the material
      ID is absent from the table or `coord_unit` is unrecognized.
    inputs:
      - name: volume_raw
        type: float
        description: Volume of the main part in (coord_unit)³, from analyze_mesh.
      - name: material_id
        type: integer
        description: Material ID of the main part, from analyze_mesh.
      - name: density_table_path
        type: string
        description: Absolute path to the Markdown density table.
      - name: coord_unit
        type: string
        description: Unit of STL vertex coordinates. One of cm, mm, m, in.
    script: scripts/compute_mass.py
    inputs_to: end

  - name: end
    kind: end
    description: Mass of the main part, with the resolved material and the volume used in the calculation.
    inputs:
      - name: mass_grams
        type: float
        description: Mass of the main part in grams.
      - name: material_name
        type: string
        description: Human-readable material name from the density table (e.g. "Unobtanium").
      - name: material_id
        type: integer
        description: Material ID that keyed the lookup.
      - name: volume_cm3
        type: float
        description: Volume of the main part in cm³ after unit conversion.
      - name: density_g_per_cm3
        type: float
        description: Density looked up from the table, in g/cm³.
      - name: total_components
        type: integer
        description: Total connected components found (≥2 implies debris was filtered out).

anti_patterns:
  - Running the computation on the whole mesh instead of the largest connected component — debris triangles inflate volume and may carry a different material ID.
  - Reading `material_id` from a stray triangle (e.g. the first triangle in the file) instead of from the largest component. Debris often sits at the start of the attribute stream.
  - Assuming STL coordinates are in cm (or mm) without checking the task description — a wrong unit gives an answer off by a factor of 1000 or 1e6.
  - Forgetting to cube the unit conversion factor when going from (coord_unit)³ to cm³.
  - Silently defaulting an unknown material ID to zero density, Generic Debris (ID 1), or any other row. The script errors out instead; investigate why the ID is missing before patching the table.
  - Parsing the STL as ASCII when it is binary — the ASCII fallback zeroes out all material IDs and the lookup then fails.
```
