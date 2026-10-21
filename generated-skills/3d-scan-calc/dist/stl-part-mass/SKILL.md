---
name: stl-part-mass
description: "Computes the mass of the main part in a noisy 3D-scan binary STL: parses triangles and the per-triangle 2-byte attribute (Material ID), filters scanning debris by keeping the largest connected component, computes its enclosed volume, looks up density by Material ID in a markdown table, and writes a JSON mass report. Use for STL volume, connected-component / debris filtering, attribute-byte material extraction, or Volume x Density mass tasks."
compatibility: "python3 >= 3.8, standard library only (struct, collections, json, re, argparse); no numpy/trimesh needed."
---

# STL Part Mass

## Trigger When

- A task asks for the mass, volume, or material of a part stored in an STL file.
- A binary STL's "Attribute Byte Count" (last 2 bytes of each 50-byte triangle record) holds a Material ID, color, or other per-triangle tag.
- Scan data contains debris/noise that must be separated from the main object (largest connected component).
- A density/material table (markdown) must be joined to mesh-derived volume (`Mass = Volume * Density`).

## Purpose

Turns a dirty scanned STL plus a material density table into a verified mass report. The script does the deterministic work (binary/ASCII parsing, shared-vertex connected components, divergence-theorem volume, watertightness check, density-table lookup, JSON output) with no third-party packages, and the agent makes only the judgments the files cannot settle: the unit scale between STL coordinates and the density's volume unit, and what to do with any warnings.

## Procedure

Check first that `python3` (>= 3.8) is available; the script needs nothing else. Name anything missing before running. Launch all commands from the skill folder (or give the script's full path); file paths are the task's real paths (e.g. `/root/scan_data.stl`).

### 1. Read the task and table (client task)

Read the task instructions and the density table. Note: input STL path, table path, output JSON path and its exact keys, the stated coordinate units (if any), and the density's units (e.g. g/cm³).

### 2. Inspect the mesh (execution)

```bash
python3 scripts/mesh_mass.py analyze /root/scan_data.stl
```

Prints format, triangle count, the components sorted by volume (triangles, volume, signed volume, Material ID counts, bounding box), the main part's edge check, and `WARNING:` lines. Nothing is written.

How it works (matches the original `MeshAnalyzer`): binary is used when file size is exactly `84 + 50*count` (or larger with trailing bytes and a header not starting with `solid`); otherwise ASCII is parsed, which has no attribute bytes, so every Material ID is 0. Triangles are connected when they share a vertex (coordinates rounded to 5 decimals). Volume = |Σ v1·(v2×v3)| / 6 per component. The main part is the component with the largest volume; its Material ID is the majority attribute of its triangles (the original took the first triangle's; same result for a uniform part).

### 3. Decide units and warnings (decision)

Answer from the task text, the table, and the analyze output:

```yaml
coordinate_units:
  type: choice
  instructions: >
    In what unit are the STL coordinates, relative to the volume unit in the density
    (e.g. cm³ in g/cm³)? Use only an explicit statement in the task or files; do not
    infer units from the size of the numbers. A false conversion (answering mm when
    nothing says so) is the costly mistake: reconsider any close call that leans
    away from same_or_unstated.
  criteria:
    same_or_unstated: Units are stated equal to the density's length unit, or not stated at all. Multiply directly; --volume-scale 1.
    mm_to_cm: Coordinates explicitly in mm, density per cm³. --volume-scale 0.001.
    m_to_cm: Coordinates explicitly in m, density per cm³. --volume-scale 1000000.
    inch_to_cm: Coordinates explicitly in inches, density per cm³. --volume-scale 16.387064.
    other: Another explicit pairing. Compute scale = (length factor to density's unit)³.
subtract_voids:
  type: noul
  instructions: >
    Only applies when analyze printed the "inward-facing shell(s) ... possible internal
    voids" warning; otherwise false. Are those shells hollow cavities of the part
    rather than separate solid pieces?
  criteria:
    true: Shells share the main Material ID, sit inside the main bounding box, and face inward (signed volume opposite to the main part's); the task does not say to use the single largest component's volume only.
    false: No void warning, or the task says to take the largest component's volume as is.
selection_ok:
  type: noul
  instructions: >
    Is the reported main part (component #0) the real object? A false "yes" is costly:
    reconsider if any of these warnings appeared: mixed Material IDs, not closed/
    consistently oriented, largest-by-volume differs from largest-by-triangle-count,
    runner-up >50% of main volume.
  criteria:
    true: No such warnings, or they are explained (e.g. a few stray-ID triangles, majority ID clearly the part's; a dense flat debris sheet with ~0 volume).
    false: Volume is untrustworthy (open/inconsistent shell) or two candidates are comparable.
```

If `selection_ok` is false, read [the method reference](references/method.md), identify the real part in the listing (closed, non-debris Material ID from the table, most triangles) and pass its listing index as `--component I` in step 4; if no candidate is closed, say the volume is unreliable in your answer.

### 4. Compute and write the report (execution)

```bash
python3 scripts/mesh_mass.py mass /root/scan_data.stl /root/material_density_table.md \
  --out /root/mass_report.json --volume-scale <scale from coordinate_units> [--subtract-voids] [--component I]
```

Add `--subtract-voids` only when `subtract_voids` is true. Writes `{"main_part_mass": <float>, "material_id": <int>}` (mass rounded to 4 decimals; change with `--decimals N`). Exits 1 with a message when the Material ID is not in the table (the message lists the table's IDs), when the table has no `ID` + `Density` columns, or when the STL is ASCII (no Material ID available; then the material must come from the task text).

### 5. Verify (client task)

`cat` the output JSON. Check keys match the task's exact format, `material_id` is the main part's ID (not a debris ID such as 0 or 1), and mass = volume × scale × density from the printed line. If the task asks for different key names or extra fields, rewrite the JSON with the computed values.

## Gotchas

- Debris can carry its own Material IDs (e.g. a "Generic Debris" row in the table): never take the ID from the whole file or the first triangle of the file, only from the main component.
- Volume is in STL units cubed. Don't assume mm or inches; with no stated units, multiply directly by the table density.
- Volume uses `abs()` of the signed sum, so a consistently inward-wound part is still correct; an inconsistently wound or open part is not (edge check catches it).
- The Python API of the original tool still works: `sys.path.append('<skill>/scripts'); from mesh_mass import MeshAnalyzer; MeshAnalyzer(path).analyze_largest_component()` returns `main_part_volume`, `main_part_material_id`, `total_components`.
