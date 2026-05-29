---
name: mesh-analysis
description: "Analyzes 3D mesh files (STL) to calculate geometric properties (volume, components) and extract attribute data. Use this skill to process noisy 3D scan data and filter debris."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Robustly process 3D STL mesh files (binary-first, ASCII fallback) to compute
  the volume of the main part, filter scan noise and debris via connected-
  component analysis, and extract the 2-byte per-triangle attribute commonly
  used to encode material IDs. Together these outputs feed downstream
  mass-from-density calculations when the task provides a material reference
  table.

trigger_when:
  - The task supplies one or more `.stl` files and asks for a geometric measurement (volume, mass, or any density-derived quantity).
  - The STL is the output of a 3D scan and may contain debris, stray triangles, or disconnected components that must be filtered before measurement.
  - The task needs the 2-byte attribute field embedded in a binary STL — typically a material ID or per-triangle color code.
  - The task supplies a material reference table (material_id → density) and asks for mass.

do_not_use_when:
  - The task supplies a non-STL mesh format (OBJ, PLY, glTF, STEP). This skill only parses STL.
  - The task asks for surface area, bounding box, centroid, curvature, or any metric other than volume / connected components / per-triangle attributes — those are not exposed by `MeshAnalyzer`.

scope_and_approval: >
  Read-only with respect to the supplied STL files. No writes, no network. Safe to
  run without confirmation.

steps:
  - name: extract-volume-and-material
    description: >
      Parse the STL, run connected-component analysis, identify the largest
      component (the main part), and return its volume, material ID, and the
      total component count. Backed by `scripts/mesh_tool.py` —
      `MeshAnalyzer.analyze_largest_component()` is the source of truth for
      parsing (binary then ASCII fallback), component splitting (vertex-
      quantised BFS at 5-decimal precision), and signed-tetrahedron volume
      integration.
    script: scripts/mesh_tool.py
    inputs:
      - name: stl_path
        type: string
        description: Absolute path to the STL file supplied by the task.
    outputs:
      - name: main_part_volume
        type: float
        description: Volume of the largest connected component, in the STL coordinate units cubed. Always positive (the integrator takes `abs`).
      - name: main_part_material_id
        type: integer
        description: The 2-byte attribute value of the first triangle in the largest component. Treat as material ID for binary STL; will be 0 for ASCII STL (the attribute field does not exist there).
      - name: total_components
        type: integer
        description: Number of connected components the mesh splits into. Values > 1 indicate the scan contains debris that was filtered out.

  - name: lookup-density
    description: >
      Resolve the density for `main_part_material_id` from the material reference
      data supplied by the task (density tables, material cards, lookup CSVs —
      whatever the task gave you). Note both the density's numeric value and its
      stated units (e.g., g/cm³, kg/m³, lb/in³) — the units flow into
      `compute-mass` and must be reconciled with the STL coordinate units. If
      the task supplies no density data, surface that as missing input rather
      than guessing.
    depends_on:
      - extract-volume-and-material
    inputs:
      - name: main_part_material_id
        type: integer
      - name: material_reference
        type: object
        description: Task-supplied mapping from material_id to (density, density_units).
    outputs:
      - name: density
        type: float
      - name: density_units
        type: string
        description: Verbatim units the task gave for density (e.g., "g/cm^3"). Do not normalise — units pass through to compute-mass.

  - name: compute-mass
    description: >
      Mass = volume × density. Before multiplying, check that the volume unit
      (the STL coordinate unit, cubed) matches the volume part of the density
      unit. If the task says coordinates are in cm and density is g/cm³,
      multiply directly. If coordinates are in mm and density is g/cm³, convert
      the volume from mm³ to cm³ (÷ 1000) before multiplying — or convert the
      density, whichever the task instructs. Never assume millimetres or inches
      from filename or convention; the task instructions are the only source of
      truth for the STL coordinate unit. If the task does not state the
      coordinate unit, surface that as a blocking ambiguity rather than picking
      a default.
    depends_on:
      - lookup-density
    inputs:
      - name: main_part_volume
        type: float
      - name: volume_units
        type: string
        description: Coordinate unit of the STL, cubed (e.g., "mm^3"). Sourced from task instructions, not from the file itself.
      - name: density
        type: float
      - name: density_units
        type: string
    outputs:
      - name: mass
        type: float
      - name: mass_units
        type: string
        description: Derived from density_units (e.g., g/cm³ → g; kg/m³ → kg).

scenarios:
  - need: Compute the volume and material ID of the main part in a noisy 3D scan.
    context: >
      Task supplies `/data/scan.stl`. The skill's `scripts/mesh_tool.py` is
      mounted at `/root/.claude/skills/mesh-analysis/scripts/mesh_tool.py`.
    action: |
      Import and call MeshAnalyzer from a Python snippet:
        import sys
        sys.path.append('/root/.claude/skills/mesh-analysis/scripts')
        from mesh_tool import MeshAnalyzer
        analyzer = MeshAnalyzer('/data/scan.stl')
        report = analyzer.analyze_largest_component()
        # report = {'main_part_volume': ..., 'main_part_material_id': ..., 'total_components': ...}
    outcome: Volume of the main part (debris excluded) plus the embedded material ID.

  - need: Run the analysis without writing Python — quick check from the shell.
    action: >
      Invoke the script's __main__ block: `python /root/.claude/skills/mesh-analysis/scripts/mesh_tool.py /data/scan.stl`.
      Output is a Python dict repr of the analysis report; parse with `ast.literal_eval`
      if you need to consume it programmatically downstream.
    outcome: Same `analyze_largest_component()` dict, printed to stdout.

  - need: Compute mass given a task-supplied density table.
    context: >
      Task instructions state coordinates are in centimetres. Material reference
      table maps material_id 7 → density 7.85 g/cm³ (carbon steel).
      `analyze_largest_component()` returned main_part_volume=42.0 and
      main_part_material_id=7.
    action: >
      Volume unit (cm³) matches the volume part of the density unit (g/cm³),
      so multiply directly: mass = 42.0 × 7.85 = 329.7 g.
    outcome: Mass in grams, with the unit derivation recorded alongside the value.

anti_patterns:
  - Assuming the STL coordinate unit is millimetres (or inches, or anything else) without checking the task instructions. STL files carry no unit metadata; the task is the only source of truth.
  - Multiplying volume × density without confirming volume_units cubed matches the volume part of density_units. A unit-mismatch error compounds — answers can be off by factors of 1000 or 16.4 silently.
  - Computing volume on the raw mesh instead of the largest connected component when the scan is noisy. Debris triangles inflate volume; that is exactly the failure mode this skill exists to prevent.
  - Trusting `main_part_material_id` from an ASCII STL. The ASCII format has no attribute field — the parser returns 0 for every triangle. If the task needs material IDs, the file must be binary STL.
  - Implementing your own STL parser or volume integrator from scratch. `MeshAnalyzer` already handles binary/ASCII detection, vertex quantisation for component analysis, and signed-tetrahedron volume — reuse it.
  - Treating `total_components > 1` as a parse error. It is the expected signal that scan debris was filtered out. The main part's volume is still trustworthy.
```
