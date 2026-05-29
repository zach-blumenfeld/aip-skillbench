---
name: mesh-analysis
description: "Analyzes 3D mesh files (binary STL) to calculate geometric properties (volume, connected components) and extract per-triangle attribute data (e.g. material IDs encoded in the 2-byte STL attribute field). Use when processing noisy 3D scan data, isolating the largest connected component, filtering debris, or computing mass from an STL plus a material density reference."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Analyze 3D mesh (STL) files for geometric properties and embedded attribute
  data. The bundled `MeshAnalyzer` (scripts/mesh_tool.py) robustly parses
  binary STL, isolates the largest connected component (filtering scan
  debris via vertex-quantized adjacency), computes signed-tetrahedron volume,
  and extracts the 2-byte per-triangle attribute commonly used as a material
  identifier. Pairs cleanly with a task-provided density reference to compute
  mass.

trigger_when:
  - Computing volume of a 3D mesh from an STL file.
  - Filtering noise or debris out of a 3D scan to recover the main object.
  - Extracting material IDs or other metadata encoded in the binary STL
    attribute bytes.
  - Computing mass of an STL part given a separate material density table or
    datasheet.

do_not_use_when:
  - The mesh is not STL (OBJ, PLY, GLTF, etc.) — different parser required.
  - Only the header or triangle count is needed (overkill).
  - The task supplies pre-computed volume and material — no parsing needed.

scope_and_approval: >
  Read-only on input meshes. Writes only to paths the task explicitly names
  (e.g., a results JSON the task asks for). No network calls. Safe to run
  without approval.

steps:
  - name: analyze-mesh
    description: >
      Parse the STL with `MeshAnalyzer` and call `analyze_largest_component()`
      to get the main part's volume, material ID, and the total component
      count. Preferred invocation is in-process Python:
        import sys
        sys.path.append('<skill-root>/scripts')
        from mesh_tool import MeshAnalyzer
        report = MeshAnalyzer(stl_path).analyze_largest_component()
      A CLI shim is also available: `python scripts/mesh_tool.py <stl_path>`
      prints the same dict. The analyzer auto-detects binary STL; on parse
      failure it falls back to ASCII (which zeroes out material IDs — flag if
      that path is hit).
    script: scripts/mesh_tool.py
    inputs:
      - name: stl_path
        type: string
        description: Filesystem path to the STL file (binary STL expected).
    outputs:
      - name: main_part_volume
        type: float
        description: Volume of the largest connected component, in the cube of the STL's coordinate units (NOT assumed to be any specific unit).
      - name: main_part_material_id
        type: integer
        description: 2-byte attribute (uint16) of triangles in the largest component; assumed uniform per component, sampled from the first triangle.
      - name: total_components
        type: integer
        description: Number of connected components after vertex-quantized (5-decimal) adjacency stitching.

  - name: lookup-density
    description: >
      Resolve `main_part_material_id` to a density by reading the task's
      material reference (markdown table, datasheet, JSON, etc.). Match by
      ID exactly. If no row matches, stop and surface the mismatch — do not
      guess a density or substitute a nearby ID.
    inputs:
      - name: main_part_material_id
        type: integer
      - name: density_reference
        type: object
        description: Task-provided material reference (e.g. /root/material_density_table.md). Must be read at runtime, not assumed.
    outputs:
      - name: density
        type: float
        description: Density value as listed in the reference, with its stated units recorded (commonly g/cm³).
      - name: density_units
        type: string
        description: Units the reference declares for `density` (e.g. "g/cm³"). Carried forward so the next step can align bases.

  - name: align-units
    description: >
      Confirm `main_part_volume` and `density` share a compatible unit basis
      before multiplying. Volume is in the STL's coordinate units cubed —
      read the task to determine those units (often mm or cm; never assumed).
      Common alignments:
        - STL in cm, density g/cm³ → no conversion.
        - STL in mm, density g/cm³ → divide volume by 1000 (1 cm³ = 1000 mm³).
        - STL in inches, density g/cm³ → convert volume (1 in³ = 16.387064 cm³).
      Record the chosen conversion factor so the result is auditable.
    inputs:
      - name: main_part_volume
        type: float
      - name: density
        type: float
      - name: density_units
        type: string
    outputs:
      - name: volume_aligned
        type: float
        description: Volume rescaled so its base matches the density's base (e.g. cm³ when density is g/cm³).
      - name: density_aligned
        type: float
        description: Usually identical to `density`; included for symmetry if the alignment instead converts density.

  - name: compute-mass
    description: >
      mass = volume_aligned * density_aligned. Plain arithmetic; do not round
      before reporting (the task's accuracy tolerance is checked against the
      full-precision value).
    inputs:
      - name: volume_aligned
        type: float
      - name: density_aligned
        type: float
    outputs:
      - name: main_part_mass
        type: float

  - name: write-report
    description: >
      Emit the result in the exact JSON shape the task specifies. The task
      prompt is authoritative on field names — do not invent or rename keys.
      For the canonical 3d-scan-calc task this is:
        { "main_part_mass": <float>, "material_id": <int> }
      written to the path the task names (e.g. /root/mass_report.json).
    inputs:
      - name: main_part_mass
        type: float
      - name: main_part_material_id
        type: integer
      - name: output_path
        type: string
    outputs:
      - name: report_path
        type: string

scenarios:
  - need: Compute the mass of a 3D-printed part from a noisy binary STL plus a density table.
    context: >
      Scan contains low-density debris fragments (tagged ID 1). The actual
      part triangles carry material ID 42 (Unobtanium, 5.55 g/cm³ in the
      provided table). Task states coordinates are in centimeters.
    action: >
      Call `MeshAnalyzer(stl).analyze_largest_component()`. The largest
      component reports a volume in cm³ and material ID 42. Look up 42 in
      the density table → 5.55 g/cm³. Units already aligned (cm³ × g/cm³),
      no conversion. Multiply for mass. Write
      `{"main_part_mass": <vol*5.55>, "material_id": 42}` to the task-named
      JSON path.
    outcome: >
      A mass value within the task's tolerance (typically ±0.1 %) and a
      JSON report matching the task's exact schema.

  - need: STL coordinates are in millimeters but density table uses g/cm³.
    context: >
      Volume from `analyze_largest_component()` is e.g. 12,000,000 (mm³),
      density is 7.85 g/cm³ for steel (ID 10).
    action: >
      Align units: 12,000,000 mm³ / 1000 = 12,000 cm³. mass = 12,000 × 7.85
      = 94,200 g. Report in whichever mass unit the task asks for.

anti_patterns:
  - Assuming millimeters, inches, or any other unit without reading the
    task — volume units follow the STL's coordinate system and the task is
    authoritative.
  - Trusting an ASCII-parse fallback for material ID. ASCII STL has no
    attribute bytes; the analyzer zeroes the ID on that path. If you see
    `mat_id == 0` and the file is supposed to be binary, treat it as a
    parse failure, not a real value.
  - Picking the first or an arbitrary component instead of the largest by
    volume. Debris often dominates by *count* (many small fragments) but
    not by volume — `analyze_largest_component()` already sorts correctly;
    don't second-guess it.
  - Re-implementing volume integration or connected-components in fresh
    code. The bundled analyzer uses the signed-tetrahedron method and a
    vertex-quantized (5-decimal) adjacency graph; both are correct and
    already debugged.
  - Rounding `main_part_mass` before writing the report. Accuracy
    tolerances (e.g. ±0.1 %) are checked against the precise value.
  - Inventing or renaming output JSON fields. The task prompt names the
    exact schema (e.g. `main_part_mass`, `material_id`); use it verbatim.
```
