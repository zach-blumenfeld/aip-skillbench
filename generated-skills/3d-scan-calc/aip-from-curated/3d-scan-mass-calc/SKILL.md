---
name: 3d-scan-mass-calc
description: "Compute the mass of a part from a noisy 3D scan: parse a binary STL, isolate the largest connected component (filtering debris), read the material_id out of the STL attribute bytes, look up the density in a provided material table, apply the coordinate-unit conversion, and return mass in grams. Use when a task hands you a scan_data.stl plus a density table and asks for the part's mass."
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
  Compute the mass of a scanned part. The input scan is a binary STL that may
  carry multiple disconnected components (the real part plus debris from a
  noisy scan) and a material ID packed into the STL attribute bytes. A script
  parses the mesh, filters to the single largest connected component, and
  returns its volume and material_id. The agent then reads the task's
  density table and emits the density in g/cm³. A second script converts
  the raw volume to cm³ using the task-declared coordinate unit and
  multiplies by density to produce mass in grams.

trigger_when:
  - The task hands over a 3D scan (STL) plus a material-density table and asks
    for a part's mass, weight, or density-derived property.
  - A scan is known or expected to contain noise, floaters, or debris that
    need to be filtered out before measurement.
  - The STL carries a material ID in its binary attribute bytes and the task
    says the material is one of several in a lookup table.

do_not_use_when:
  - The task provides a clean, single-component mesh and the material is
    already identified — a direct volume×density calculation is enough.
  - The input is not an STL (e.g., OBJ, PLY, STEP), or the task asks for a
    non-mass quantity the mesh analyzer does not expose (surface area,
    bounding box, printability).
  - No density table is supplied and the task does not name the material.

steps:
  - name: analyze-mesh
    kind: execution
    description: Parse the binary STL, filter to the largest connected component, and emit its volume + material_id.
    inputs:
      - name: stl_path
        type: string
        description: Absolute path to the binary STL scan file.
      - name: density_table_path
        type: string
        description: Absolute path to the markdown material/density lookup table. Passed through to the lookup step.
      - name: stl_coord_unit
        type: string
        description: Unit of the STL coordinate system — one of "mm", "cm", "m", "in". Taken from the task instructions; the STL file itself does not record it. Passes through to the mass-computation step.
    script: scripts/analyze_mesh.py
    inputs_to: lookup-density

  - name: lookup-density
    kind: client_task
    description: Read the material-density table and emit the density of the main part in g/cm³.
    inputs:
      - name: density_table_path
        type: string
      - name: main_part_material_id
        type: integer
      - name: main_part_volume
        type: float
      - name: total_components
        type: integer
      - name: stl_coord_unit
        type: string
    template: assets/lookup_density.md
    references:
      - path: references/units-and-density.md
        description: Load if the density table uses a unit other than g/cm³, or if the volume unit is unclear. Lists conversion factors and the main gotchas when parsing a markdown density table.
    inputs_to: compute-mass

  - name: compute-mass
    kind: execution
    description: Convert the raw volume to cm³ using stl_coord_unit, then multiply by density to produce mass in grams.
    inputs:
      - name: main_part_volume
        type: float
      - name: stl_coord_unit
        type: string
      - name: density_g_per_cm3
        type: float
      - name: main_part_material_id
        type: integer
      - name: total_components
        type: integer
    script: scripts/compute_mass.py
    inputs_to: end

  - name: end
    kind: end
    description: Mass in grams plus the intermediate quantities used to derive it.
    inputs:
      - name: mass_g
        type: float
        description: Final mass of the main part, grams.
      - name: volume_cm3
        type: float
        description: Volume of the main part in cm³ (after unit conversion).
      - name: main_part_volume
        type: float
        description: Raw volume returned by the mesh analyzer, in the cube of stl_coord_unit.
      - name: main_part_material_id
        type: integer
      - name: density_g_per_cm3
        type: float
      - name: total_components
        type: integer

anti_patterns:
  - Running volume × density on all triangles in the STL (summing debris with the real part) instead of first isolating the largest connected component.
  - Assuming the STL is in millimeters. The STL format carries no unit; take it from the task instructions and pass it as stl_coord_unit.
  - Multiplying volume (in the STL's unit cubed) by a density given in a different volume unit without converting — e.g., mm³ volume × g/cm³ density is wrong by 1000×.
  - Reading material_id out of ASCII STL. Binary STL stores the ID in the 2-byte attribute per triangle; ASCII does not carry it and the parser defaults to 0.
  - Guessing a density when the material_id is missing from the table instead of surfacing the gap.
```
