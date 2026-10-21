---
name: stl-part-mass
description: Compute the mass of the main part in a noisy binary STL 3D scan whose per-triangle attribute bytes store a Material ID. Parses binary/ASCII STL, filters scanning debris by keeping the largest connected component by volume, extracts the Material ID, looks up density in a markdown material density table, and writes Mass = Volume * Density to a JSON report. Use for STL volume, mass, material ID, attribute byte, debris filtering, or connected-component tasks.
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
  Compute the mass of the main part in a noisy binary STL scan whose per-triangle
  2-byte "Attribute Byte Count" stores a Material ID. A script parses the STL, groups
  triangles into connected components by shared vertices, keeps the largest component
  by volume (everything else is scanning debris), reads its Material ID, and looks the
  density up in a markdown density table; a decision settles the coordinate units from
  the task statement; a script computes Mass = Volume * Density and writes the JSON
  report. Standard library only, so it runs on a bare python3 container.

trigger_when:
  - A task asks for the mass, weight, or volume of a part in an STL file, especially a 3D scan with debris or noise.
  - A binary STL stores a material ID, color, or other metadata in the per-triangle attribute bytes.
  - A Material ID must be matched against a density or material table to compute mass.
  - The largest connected component of a mesh must be isolated from scanning debris.

do_not_use_when:
  - The mesh is not STL (OBJ, PLY, STEP) or the task needs mesh repair, remeshing, or rendering.
  - The task wants every component's mass or the total of all components rather than the main part.

requires:
  interpreter:
    name: python
    version: "3.8"

steps:
  - name: analyze-scan
    kind: execution
    description: >
      Parse the STL (binary when the file size equals 84 + 50 * triangle_count, even if the
      header starts with "solid"; the 2-byte attribute after each triangle's 12 floats is
      the Material ID), group triangles sharing a vertex (coordinates rounded to 5 decimals)
      into components, keep the one with the largest absolute signed-tetrahedron volume,
      take its majority Material ID, and look up that ID's density in the markdown table.
      Exits non-zero if the ID is not in the table.
    inputs:
      - name: stl_path
        type: string
        description: Path to the STL scan, e.g. /root/scan_data.stl.
      - name: density_table_path
        type: string
        description: Path to the markdown density table, e.g. /root/material_density_table.md.
      - name: report_path
        type: string
        description: Where compute-mass writes the JSON report, e.g. /root/mass_report.json. Not read by this script.
      - name: task_statement
        type: string
        description: The task's instructions, verbatim; settle-units reads it for the coordinate unit. Not read by this script.
    script: scripts/analyze_scan.py
    outputs:
      - name: main_part_volume
        type: float
        description: Volume of the largest component, in the STL's coordinate units cubed.
      - name: material_id
        type: integer
        description: Material ID from the largest component's attribute bytes.
      - name: density
        type: float
        description: Density for that Material ID, as written in the table.
      - name: density_unit
        type: string
        description: The density column header, which carries its unit (e.g. "Density (g/cm³)").
      - name: material_name
        type: string
        description: Material name from the table row, empty if the table has no name column.
      - name: mesh_report
        type: object
        description: Format, triangle and component counts, the five largest components, debris volume, table IDs, and warnings (mixed IDs, open edges, ASCII fallback).
    inputs_to: settle-units

  - name: settle-units
    kind: decision
    description: Decide which unit the STL coordinates are in, so volume and density units agree.
    inputs:
      - name: task_statement
        type: string
      - name: density_unit
        type: string
      - name: mesh_report
        type: object
    questions:
      coordinate_units:
        type: choice
        instructions: >
          In what unit are the STL coordinates? The STL format carries no units and the
          computed volume is in coordinate units cubed. Answer from what the task statement
          explicitly says about the STL or CAD coordinates. Do not assume millimeters or
          inches because 3D printing usually uses them, and do not infer units from the
          density table's unit or from how large the numbers look: when the task does not
          state the coordinate unit, or states the same length unit the density uses, the
          answer is same_as_table and the volume is multiplied by the density directly.
        criteria:
          same_as_table: The task gives no coordinate unit, or gives the same length unit as the density table (e.g. cm with g/cm³). Multiply directly, no conversion.
          millimeters: The task explicitly says the coordinates are in millimeters and the density uses a different length unit.
          centimeters: The task explicitly says the coordinates are in centimeters and the density uses a different length unit (e.g. kg/m³).
          meters: The task explicitly says the coordinates are in meters and the density uses a different length unit.
          inches: The task explicitly says the coordinates are in inches.
    thresholds:
      coordinate_units: 0.3
    inputs_to: compute-mass

  - name: compute-mass
    kind: execution
    description: >
      Mass = Volume * Density. same_as_table multiplies directly; an explicit unit converts
      the volume to cm³ and the density to g/cm³ (mass in grams). Writes
      {"main_part_mass": <float>, "material_id": <int>} to report_path.
    inputs:
      - name: main_part_volume
        type: float
      - name: material_id
        type: integer
      - name: density
        type: float
      - name: density_unit
        type: string
      - name: coordinate_units
        type: string
      - name: report_path
        type: string
    script: scripts/compute_mass.py
    outputs:
      - name: main_part_mass
        type: float
        description: Mass of the main part, rounded to 4 decimals.
      - name: mass_report
        type: object
        description: The exact JSON object written to report_path.
    inputs_to: end

  - name: end
    kind: end
    description: The main part's mass and Material ID, written to report_path.
    inputs:
      - name: main_part_mass
        type: float
      - name: material_id
        type: integer
      - name: material_name
        type: string
      - name: main_part_volume
        type: float
      - name: mesh_report
        type: object
      - name: mass_report
        type: object

anti_patterns:
  - Computing volume or mass over the whole file; the debris components must be excluded.
  - Picking the main part by triangle count or bounding box instead of volume.
  - Reading the Material ID from the file header or a debris triangle instead of the largest component's attribute bytes.
  - Treating the file as ASCII because its 80-byte header starts with "solid"; the size check decides.
  - Converting units (e.g. assuming mm and dividing by 1000) when the task gives no coordinate unit.
  - Guessing a density when the Material ID is not in the table, or hardcoding an expected mass or ID.
  - Writing the report with extra keys, a string mass, or a non-integer material_id.
```
