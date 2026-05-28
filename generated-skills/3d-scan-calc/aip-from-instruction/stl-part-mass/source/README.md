# Source & authoring notes — `stl-part-mass`

## Intent

Equip an autonomous agent to solve the `3d-scan-calc` task: given a binary STL
at `/root/scan_data.stl` whose per-triangle "Attribute Byte Count" stores a
Material ID, and a markdown density table at `/root/material_density_table.md`,
compute the main part's mass and write `/root/mass_report.json` as
`{"main_part_mass": <float>, "material_id": <int>}` to within 0.1% accuracy.

Authored **from `instruction.md` alone** (bundled here as the canonical
source). No existing skill was inspected.

## Schema choice

`procedure.schema.json` (reused, unmodified) — the task is a deterministic
multi-step pipeline (parse → component-filter → volume → material → density →
mass → write), which is exactly the procedure category. No new schema needed.

## Why the logic lives in a script

Per AIP best practice, numeric calculation + lookup-table + binary-format
parsing must be script-backed for consistency. `scripts/compute_mass.py` is the
single source of truth for: binary STL parsing (`<12fH` records), union-find
connected components by shared vertex, signed-tetrahedron volume, Material-ID
extraction (mode of main-component attributes), markdown density-table parsing,
and unit conversion. The SKILL.md body is the execution graph around it; the
unit gotcha is kept in the body and in `references/stl-binary-format.md` so the
agent verifies before trusting the number.

## Source content → body mapping (completeness check)

Every distinct requirement in `instruction.md`:

- "binary STL" + attribute-byte = Material ID → **Mapped**: parse step, script
  `RECORD_FMT="<12fH"`, attribute read as uint16, reference doc.
- "largest connected component / filter scanning debris" → **Mapped**: compute
  step + `find_components`/`largest_component`; anti-pattern against summing all.
- "Extract Material ID and reference /root/material_density_table.md for
  density" → **Mapped**: read-inputs + compute steps; `parse_density_table`.
- "mass = Volume * Density" → **Mapped**: `mesh_volume` × density in compute step.
- output file `/root/mass_report.json` with exact `{main_part_mass, material_id}`
  shape → **Mapped**: compute writes it; verify step checks shape.
- "within 0.1% accuracy" → **Mapped**: float64 accumulation; anti-pattern
  against rounding to 2 decimals; unit-conversion handling.

**Deliberate additions beyond the literal instruction** (the instruction is
terse; these are the non-obvious knowledge an agent needs and are justified):
- Unit conversion (mm coords vs g/cm^3 density). The instruction omits units,
  but a raw multiply is a 1000×-per-power error. Auto-detect + overrides +
  loud stderr so the agent can verify against the table it reads at runtime.
- Material ID via the *most common* attribute in the main component (debris may
  carry different values); the instruction implies one ID per object.

No source content was dropped.

## Tested

Synthetic STL (unit cube of 12 triangles, Material ID 42 + a 4-triangle debris
tetrahedron, ID 7) with a g/cm^3 density table: script selected the 12-triangle
component, volume = 1.0 mm^3, Material ID 42, mass = 1.0 × 1e-3 × 2.70 =
0.0027 g. Component filtering, volume, ID extraction, density lookup, and unit
conversion all verified.
