---
name: stl-mass-calc
description: Compute the mass of a 3D-printed part from a noisy binary-STL scan whose per-triangle attribute bytes encode a Material ID. Parses the STL, filters debris by keeping the largest connected component, looks up the density for the extracted Material ID in a provided markdown density table, multiplies volume by density, and writes a JSON report. Use when a task provides a binary STL plus a density table and asks for the main part's mass; also usable for mesh volume, largest-component filtering, or STL attribute-byte extraction on their own.
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
  Turn a noisy binary-STL scan into the mass of its main part. Analyze the mesh
  to isolate the largest connected component (filtering debris) and extract its
  volume and the Material ID stored in each triangle's attribute bytes. Then
  parse a markdown density table, look up the density for that Material ID,
  multiply volume by density, and write the result to a JSON report file.
  Units flow through untouched: the caller must supply an STL and a density
  table whose length units already agree (e.g. cm coords with g/cm^3 gives g).

trigger_when:
  - A task provides a binary STL and a density table and asks for the main part's mass.
  - A 3D scan contains debris and only the largest connected component should be measured.
  - Only mesh volume, largest-component filtering, or STL attribute-byte extraction is needed.

do_not_use_when:
  - The STL's coordinate units and the density table's length units differ and no unit conversion is provided upstream.
  - The Material ID is not encoded in the STL attribute bytes (ASCII STL, or a different attribute convention).
  - The task needs a full mesh-repair or watertightness fix beyond largest-component filtering.

steps:
  - name: analyze-mesh
    kind: execution
    description: >
      Parse the binary STL, group triangles into connected components by shared
      vertices (quantized to 5 decimals), select the component with the largest
      absolute signed-tetrahedron volume as the main part, and return that
      component's volume plus its Material ID (read from the first triangle's
      2-byte attribute field, which is uniform per component in this format).
      Falls back to ASCII parsing if binary parsing fails, in which case the
      Material ID will be 0 because ASCII STL has no attribute bytes.
    inputs:
      - name: stl_path
        type: string
        description: Absolute path to the binary STL file to analyze.
    script: scripts/analyze_mesh.py
    inputs_to: compute-mass-report

  - name: compute-mass-report
    kind: execution
    description: >
      Parse the material density table (markdown with rows like
      `| **10** | Standard Steel | 7.85 | ... |`), look up the density for the
      extracted Material ID, compute mass = volume * density, and write
      `{"main_part_mass": <float>, "material_id": <int>}` to `output_path` as
      JSON. Exits non-zero if the Material ID is not present in the table.
      Does no unit conversion — length units in the STL must already match the
      density table's length units.
    inputs:
      - name: main_part_volume
        type: float
        description: Volume of the main part, in the STL's coordinate units cubed.
      - name: material_id
        type: integer
        description: Material ID extracted from the main part's attribute bytes.
      - name: density_table_path
        type: string
        description: Absolute path to the markdown density table.
      - name: output_path
        type: string
        description: Absolute path where the JSON mass report should be written.
    script: scripts/compute_mass_report.py
    inputs_to: end

  - name: end
    kind: end
    description: >
      The JSON report at `report_path` contains exactly two keys —
      `main_part_mass` and `material_id` — matching the format the caller
      expects on disk. The final state additionally exposes `density` (the
      value looked up in the table) for auditing; that key lives only in the
      run state, not in the report file.
    inputs:
      - name: main_part_mass
        type: float
      - name: material_id
        type: integer
      - name: report_path
        type: string
      - name: density
        type: float

anti_patterns:
  - Computing mass over all triangles instead of filtering to the largest connected component — debris inflates the volume.
  - Assuming STL coordinates are millimeters or inches and converting; the tool preserves whatever units the file uses.
  - Hard-coding a density table inside the skill instead of parsing the one the caller provides; the table can change per task.
  - Trusting an ASCII-STL fallback for Material ID — ASCII STL has no attribute bytes, so `material_id` will be 0 and the density lookup will fail.
```
