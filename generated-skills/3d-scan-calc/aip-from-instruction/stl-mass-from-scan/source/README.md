# Source notes — `stl-mass-from-scan`

## Origin

Authored from `vendor/skillsbench/tasks/3d-scan-calc/instruction.md` only,
under aip-from-instruction mode. No prior human skill was consulted.

## Task summary (paraphrased)

Compute mass of a 3D-printed part scanned into `/root/scan_data.stl`. The
binary STL repurposes each triangle's 2-byte "Attribute Byte Count" as a
**Material ID**. The scan may contain debris — the actual part is the
largest connected component. Look up density for the part's Material ID
in `/root/material_density_table.md` and emit:

```json
{ "main_part_mass": <float>, "material_id": <int> }
```

at `/root/mass_report.json`. Tolerance is 0.1%.

## Schema choice

Reused `procedure.schema.json` from `assets/aip-schemas/`. The task is a
linear procedure with a few decisions — exactly what that schema covers.
No new schema needed.

## Why these steps

- **parse-stl** isolates the binary-format gotcha (50-byte records, the
  attribute-byte-count repurposing) so it cannot be missed.
- **find-largest-component** is the explicit "filter out scanning debris"
  instruction reified as union-find on shared vertices.
- **derive-material-id** uses the mode across the component's triangles
  rather than trusting one record — defensive against stray words.
- **compute-volume** locks in the signed-tetrahedron formula.
- **lookup-density** + **assemble-mass** separate the unit-handling step
  from the volume math; units are where 0.1% tolerance breaks down.
- **write-output** pins the exact JSON shape.

A single self-contained script (`scripts/compute_mass.py`) implements all
of the above; the procedure tells the agent to prefer the script and to
verify its assumptions (units, component count) via `--verbose` before
trusting the output.

## Source content classification

- **Mapped** — binary STL parsing, attribute-byte-count → Material ID,
  largest-connected-component filter, density lookup, mass formula,
  output JSON shape, 0.1% tolerance.
- **Deliberate drop** — none. Every concrete instruction in the source
  is reflected in either the procedure body, the script, or the binary
  STL reference.
