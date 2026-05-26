---
name: mesh-analysis
description: "Analyzes 3D mesh files (STL) to calculate geometric properties (volume, components) and extract attribute data. Use this skill to process noisy 3D scan data and filter debris."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Process 3D STL mesh files via the bundled `MeshAnalyzer` Python tool to
  compute volume, isolate the largest connected component (filtering noisy
  scan debris), and extract per-triangle attribute bytes (commonly material
  IDs) from Binary STL. The skill stops at geometric properties — mass
  requires combining the reported volume with an external density lookup.

trigger_when:
  - Calculating volume of complex or noisy 3D meshes.
  - Isolating the main part from "dirty" scan data containing debris or stray components.
  - Extracting material IDs or other 2-byte attributes from Binary STL files.
  - User mentions STL files, 3D scans, mesh analysis, or component filtering.

steps:
  - name: load-mesh
    description: >
      Import `MeshAnalyzer` from `scripts/mesh_tool.py` (add the skill's
      `scripts/` directory to `sys.path` first) and instantiate it with the
      absolute path to the STL file. Parsing happens in the constructor;
      Binary STL is attempted first, with ASCII fallback (ASCII loses
      material IDs).
  - name: analyze-largest-component
    description: >
      Call `analyzer.analyze_largest_component()`. The returned dict contains
      `main_part_volume`, `main_part_material_id`, and `total_components`.
      This automatically filters debris by selecting the highest-volume
      connected component.
  - name: derive-mass-if-needed
    description: >
      If the task requires mass, look up the density for
      `main_part_material_id` in the task-provided material reference, then
      compute `mass = volume * density`. Verify that the density's volume
      unit matches the STL coordinate unit before multiplying — no
      conversion is needed when units already match.

decisions:
  - signal: STL contains debris or multiple disconnected pieces.
    action: Use `analyze_largest_component()` rather than `get_volume()` over all triangles; the latter sums every component including noise.
  - signal: Need per-component detail beyond just the largest.
    action: Call `analyzer.get_components()` to get the full list of components, then `analyzer.get_volume(component)` on each.
  - signal: Binary parse fails and the tool falls back to ASCII.
    action: Material IDs will be 0 for every triangle. Treat material-ID-derived results as unavailable and surface this to the user.
  - signal: Task specifies coordinate units (e.g., cm, mm, inches).
    action: Report volume in those units cubed; pick a density table that uses the same unit so multiplication is direct.

anti_patterns:
  - Assuming the volume is in mm³ or in³ by default — units come from the STL coordinates and must be read from the task instructions.
  - Converting density units when the density table already matches the STL's coordinate unit.
  - Summing volume over all triangles when the scan contains debris — use `analyze_largest_component()` to filter first.
  - Treating ASCII STL material IDs as meaningful — only Binary STL carries the 2-byte attribute.
```
