---
name: stl-scan-mass
description: Computes the mass of the main part in a noisy 3D scan stored as an STL file (binary STL with material IDs in the 2-byte attribute field). Splits the mesh into connected components, drops scan debris by keeping the largest-volume component, reads its material ID, looks up the density in a material density table (markdown/CSV), converts units, and reports Mass = Volume × Density. Use for STL volume, mesh mass/weight, material-ID extraction, 3D scan debris filtering, or CAD part mass questions.
metadata:
  aip-version: "0.5a1"
compatibility: Scripts use only the Python 3 standard library (no numpy/trimesh needed).
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
  Compute the mass of the real object in a noisy 3D scan (STL). Scan files carry the part
  plus disconnected debris; the part is the largest connected component by enclosed volume,
  its material ID lives in the binary STL per-triangle 2-byte attribute, and its density
  comes from a material table keyed by that ID. Volume is in the STL coordinate unit cubed,
  so it is converted to the density table's volume unit before Mass = Volume x Density.
  Scripts do parsing, component analysis, lookup, and unit math; the agent only resolves
  flagged anomalies and writes the answer in the format the task asks for.

trigger_when:
  - A task asks for the mass, weight, or volume of an object in an STL / 3D scan / CAD mesh file.
  - A task gives an STL plus a material density table keyed by material ID.
  - A task asks to filter scan noise or debris and measure only the main part.
  - A task asks to extract material IDs or color/attribute data from binary STL attribute bytes.

do_not_use_when:
  - The mesh is in another format (OBJ, PLY, STEP, glTF) and no STL is available.
  - The task wants mesh repair, remeshing, rendering, or printing, not measurement.

steps:
  - name: analyze-mesh
    kind: execution
    description: Parse the STL (binary, ASCII fallback), split into connected components, and report the largest-volume component's volume and material ID plus a ranked component list.
    inputs:
      - name: stl_path
        type: string
        description: Absolute path to the STL file named in the task (e.g. /root/scan_data.stl).
      - name: density_table_path
        type: string
        description: Absolute path to the material density table (markdown or CSV) named in the task.
      - name: coordinate_unit
        type: string
        description: Length unit of the STL coordinates as stated in the task (mm, cm, m, in, ft), or "unspecified" if the task gives none. Never guess mm or inches.
    script: scripts/analyze_mesh.py
    timeout: 300
    inputs_to: compute-mass

  - name: compute-mass
    kind: execution
    description: Look up the material's density by ID, convert the volume from coordinate_unit^3 to the density's volume unit, compute mass, and flag anything that needs review.
    inputs:
      - name: main_part_volume
        type: float
        description: Volume of the largest component, in STL coordinate units cubed.
      - name: main_part_material_id
        type: integer
        description: Most common non-zero attribute value on the main part's triangles (0 = none).
      - name: density_table_path
        type: string
      - name: coordinate_unit
        type: string
    script: scripts/compute_mass.py
    inputs_to: check-mass

  - name: check-mass
    kind: router
    description: Clean results go straight to reporting; any flagged issue goes to review first.
    branch_on: mass_status
    branches:
      ok: report-answer
      needs_review: resolve-material

  - name: resolve-material
    kind: client_task
    description: Resolve the flagged issues (unknown material ID, unit, debris-labelled material, open shell) with overrides or acknowledge them, then recompute.
    inputs:
      - name: mass_issues
        type: list[*]
      - name: components
        type: list[*]
      - name: main_part_attribute_histogram
        type: object
    template: assets/resolve-material.md
    references:
      - path: references/stl-format.md
        description: Binary STL byte layout, attribute/material-ID field, volume formula, component rule, and how to inspect the mesh by hand. Load if the file failed to parse or the material ID or component ranking looks wrong.
    inputs_to: compute-mass

  - name: report-answer
    kind: client_task
    description: Write the mass (and any other requested values) in exactly the location, format, unit, and rounding the task asks for.
    inputs:
      - name: mass
        type: float
      - name: mass_unit
        type: string
      - name: material_id_used
        type: integer
    template: assets/report-answer.md
    inputs_to: end

  - name: end
    kind: end
    description: Mass of the scan's main part, reported where the task wants it.
    inputs:
      - name: mass
        type: float
        description: Mass of the main part in mass_unit (the density table's mass unit unless converted on report).
      - name: mass_unit
        type: string
      - name: answer_location
        type: string
        description: Path the answer was written to, or "chat".
      - name: reported_mass
        type: float
        description: The mass exactly as reported (after any unit conversion or rounding the task asked for).
      - name: reported_unit
        type: string
        description: Unit of reported_mass (e.g. g, kg).

anti_patterns:
  - Summing the volume of every component; scan debris is separate components and must be excluded.
  - Picking the main part by triangle count instead of enclosed volume.
  - Taking the material ID from the first triangle only; unset (0) attributes can be mixed in, so use the dominant non-zero ID.
  - Assuming STL coordinates are millimeters or inches. Use the unit the task states; if it states none and the density table is per cm³, the coordinates are taken as cm and multiplied directly.
  - Converting units twice, e.g. dividing by 1000 when coordinates and density are both already in cm.
  - Rounding intermediate volume or density; round only the final reported value, and only if the task asks.
  - Ignoring a material the task explicitly names. The file's attribute ID is the default source of the material; if the task states the part's material and it differs, follow the task by putting material_id_override (the table ID) in the start state, and mention the conflict when reporting.
  - Typing a mass in by hand during review instead of setting overrides and letting compute-mass recompute.
  - Printing diagnostics to stdout from a step script; stdout must stay a single JSON object.
```
