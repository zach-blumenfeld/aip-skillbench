---
name: stl-part-mass
description: >
  Compute the mass of a 3D-printed/scanned part from a binary STL whose
  per-triangle "Attribute Byte Count" field is repurposed to store a Material
  ID. Parses the binary STL, isolates the largest connected component (drops
  scanning debris), computes enclosed volume, looks up density by Material ID
  in a markdown density table, applies unit conversion, and writes a mass
  report JSON. Use when asked to calculate part mass/weight from an STL,
  extract a Material ID embedded in STL attribute bytes, find the main part
  in a noisy scan mesh, or compute volume*density from a mesh.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.11+ (standard library only). Run scripts/compute_mass.py with `uv run` or `python3`.
---

```yaml
purpose: >
  Calculate the mass of the main part in a binary STL scan whose 2-byte
  per-triangle "Attribute Byte Count" is repurposed to store the object's
  Material ID. The mesh contains scanning debris (small disconnected
  islands) that must be filtered out by keeping only the largest connected
  component. Mass = enclosed-volume * density, where density is looked up by
  Material ID in a markdown table. The hard parts an agent gets wrong unaided:
  the exact binary layout, reading the Material ID from the attribute field,
  vertex-based component detection, the signed-tetrahedron volume formula, and
  unit conversion between STL coordinates (mm) and density (usually g/cm^3).

trigger_when:
  - Asked to compute the mass or weight of a part from a binary STL file.
  - An STL stores a Material ID in the per-triangle attribute-byte-count field.
  - A scan mesh contains debris and you must isolate the main/largest part.
  - You must compute volume * density from a triangulated mesh.

do_not_use_when:
  - The input is an ASCII STL (no binary attribute field to carry a Material ID).
  - You only need surface area, bounding box, or a count of parts — not mass.

scope_and_approval: >
  Read-only on inputs (/root/scan_data.stl, /root/material_density_table.md).
  The only write is the result file (default /root/mass_report.json). No other
  side effects; safe to run without approval.

steps:
  - name: read-inputs
    description: >
      Confirm the two inputs exist and READ the density table so you know the
      density unit and column layout before computing. Default paths:
      /root/scan_data.stl and /root/material_density_table.md.
    outputs:
      - name: density-table-text
        type: string
        description: Raw markdown so you can confirm the density unit (e.g. g/cm^3) and columns.
  - name: compute
    description: >
      Run the full pipeline. The script parses the binary STL, finds the
      largest connected component by shared vertices, computes its enclosed
      volume (signed-tetrahedron sum), reads the Material ID (most common
      attribute in the main component), looks up density, applies unit
      conversion (STL coords assumed mm; density length unit auto-detected
      from the table header), and writes the report. Diagnostics print to
      stderr — read them to sanity-check counts, volume, material, and the
      unit conversion factor.
    script: scripts/compute_mass.py
    inputs:
      - name: density-table-text
        type: string
    outputs:
      - name: main_part_mass
        type: float
        description: Mass in the density's mass unit (grams when density is g/cm^3). Not pre-rounded.
      - name: material_id
        type: integer
        description: Material ID read from the main component's attribute bytes.
  - name: verify-units-and-report
    description: >
      Cross-check the stderr diagnostics against the density table you read.
      Confirm the detected density length unit matches the table header and
      that the coordinate-unit assumption (mm) is right. If the table states a
      different coordinate unit or the units already match, re-run with
      --coord-unit / --density-unit / --no-unit-convert. Confirm the result
      file matches the required schema exactly.
    inputs:
      - name: main_part_mass
        type: float
      - name: material_id
        type: integer
    outputs:
      - name: report-path
        type: string
        description: Path to the written JSON, default /root/mass_report.json.

scenarios:
  - need: Mass of a scanned aluminium bracket; mesh has stray debris triangles.
    context: >
      STL has 50k triangles in 3 components (sizes 49,980 / 15 / 5). Attribute
      bytes hold 42 on the main part. Density table lists ID 42 -> 2.70 g/cm^3.
    action: >
      Run compute_mass.py. Largest component (49,980 tris) is kept; volume
      computed in mm^3; coords mm and density per cm^3 -> volume *1e-3 before
      multiplying.
    outcome: >
      mass_report.json = {"main_part_mass": <V_mm3 * 1e-3 * 2.70>, "material_id": 42}.

anti_patterns:
  - Summing volume over ALL triangles instead of only the largest component — debris inflates the mass.
  - Reading the attribute field as anything but a little-endian uint16, or ignoring it.
  - Multiplying volume*density with no unit conversion when coords are mm and density is per cm^3 (1000x error per power).
  - Rounding main_part_mass to 2 decimals like the example — that can exceed the 0.1% tolerance for small masses. Write the full float.
  - Treating the file as ASCII STL, or hand-parsing records and miscounting the 50-byte stride.
  - Computing volume from triangle normals/areas instead of the signed-tetrahedron sum.
```
