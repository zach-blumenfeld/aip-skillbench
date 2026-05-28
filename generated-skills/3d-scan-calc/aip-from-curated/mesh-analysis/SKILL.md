---
name: mesh-analysis
description: "Analyzes 3D mesh files (STL) to calculate geometric properties (volume, components) and extract attribute data. Use this skill to process noisy 3D scan data and filter debris."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3 (standard library only — struct, collections). No third-party mesh libraries needed.
---

```yaml
purpose: >
  Process 3D STL mesh files via the bundled `MeshAnalyzer` Python tool
  (`scripts/mesh_tool.py`) to compute volume, isolate the largest connected
  component (filtering noisy scan debris), and extract per-triangle attribute
  bytes (commonly material IDs) from Binary STL. The skill stops at geometric
  properties; mass is derived by combining the reported volume with a
  task-supplied density lookup. Units come from the STL coordinates and must
  be read from the task — never assumed.

trigger_when:
  - Calculating the volume of complex or noisy 3D meshes.
  - Isolating the main part from "dirty" scan data containing debris or stray disconnected components.
  - Extracting material IDs or other 2-byte attributes from Binary STL files.
  - Deriving the mass of a scanned part from its volume and a material density.
  - User mentions STL files, 3D scans, mesh analysis, connected components, or debris filtering.

do_not_use_when:
  - The task asks for surface area, dimensions, or a non-volumetric property the tool does not compute.
  - The input is a mesh format other than STL (e.g. OBJ, PLY) — the parser is STL-specific.

scope_and_approval: >
  Read-only on the input STL file. The tool parses bytes and computes
  in-memory; it performs no writes, no network calls, and no destructive
  operations. Safe to run without prompting. Any output file the task
  requires is written by the agent, not by the tool.

steps:
  - name: load-mesh
    description: >
      Import `MeshAnalyzer` from `scripts/mesh_tool.py` (add the skill's
      `scripts/` directory to `sys.path` first) and instantiate it with the
      absolute path to the STL file. Parsing happens in the constructor:
      Binary STL is attempted first (validating size == 84 + 50*N), with an
      ASCII fallback that loses material IDs (all set to 0).
    script: scripts/mesh_tool.py
    inputs:
      - name: stl-path
        type: string
        description: Absolute path to the STL file to analyze.
    outputs:
      - name: analyzer
        type: object
        description: A MeshAnalyzer holding the parsed triangles (each triangle is v1, v2, v3, material_id).
  - name: analyze-largest-component
    description: >
      Call `analyzer.analyze_largest_component()`. It runs connected-component
      analysis over shared (quantized) vertices, selects the highest-volume
      component to filter debris, and returns a dict with `main_part_volume`,
      `main_part_material_id`, and `total_components`. For per-component detail
      beyond the largest, call `analyzer.get_components()` then
      `analyzer.get_volume(component)` on each.
    script: scripts/mesh_tool.py
    depends_on: [load-mesh]
    inputs:
      - name: analyzer
        type: object
    outputs:
      - name: main_part_volume
        type: float
        description: Volume of the largest connected component, in the STL's coordinate units cubed.
      - name: main_part_material_id
        type: integer
        description: The 2-byte attribute of the component's first triangle (0 under ASCII fallback).
      - name: total_components
        type: integer
        description: Number of connected components found (debris pieces inflate this).
  - name: derive-mass-if-needed
    description: >
      Only if the task requires mass. Look up the density for
      `main_part_material_id` in the task-supplied material reference (e.g. a
      density table), then compute `mass = volume * density`. The volume is in
      the STL coordinate units cubed — read those units from the task; do not
      assume mm or inches. When the density's volume unit already matches the
      STL unit (e.g. g/cm^3 with cm coordinates), multiply directly with no
      conversion. This step stays prose because the density source's location
      and format are task-specific and unknown to the tool.
    depends_on: [analyze-largest-component]
    inputs:
      - name: main_part_volume
        type: float
      - name: main_part_material_id
        type: integer
    outputs:
      - name: mass
        type: float
        nullable: true
        description: volume * density in the matched unit system; null when the task does not ask for mass.

scenarios:
  - need: Scan contains the part plus debris or several disconnected pieces.
    action: >
      Use `analyze_largest_component()`, not `get_volume()` over all triangles.
      The latter sums every component including noise, inflating the result.
    outcome: Volume and material ID reflect only the main part.
  - need: Need volume or material ID for each component, not just the largest.
    action: Call `analyzer.get_components()` for the full list, then `analyzer.get_volume(component)` on each.
    outcome: Per-component breakdown for custom selection logic.
  - need: Binary parse fails and the tool falls back to ASCII.
    context: The constructor prints a "Binary parse failed ... Falling back to ASCII" notice.
    action: Treat every `material_id` as 0 and surface that material-derived results (including mass) are unavailable.
    outcome: Geometric volume is still valid; material-keyed lookups are not.
  - need: Task specifies coordinate units (e.g. cm, mm, inches).
    action: Report volume in those units cubed and pick a density table whose volume unit matches, so the multiply is direct.
    outcome: Mass computed without any unit conversion.

anti_patterns:
  - Assuming volume is in mm^3 or in^3 by default — units come from the STL coordinates and must be read from the task instructions.
  - Converting density units when the density table already uses the STL's coordinate unit — multiply directly instead.
  - Summing volume over all triangles when the scan contains debris — use `analyze_largest_component()` to filter first.
  - Treating ASCII-STL material IDs as meaningful — only Binary STL carries the 2-byte attribute; the ASCII fallback sets every ID to 0.
  - Trusting `main_part_material_id` for a component whose triangles carry mixed IDs — it reports only the first triangle's attribute and assumes the ID is uniform across the component. If mixed IDs are possible, inspect the component's triangles directly via `get_components()`.
```
