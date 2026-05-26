---
name: stl-mass-from-scan
description: Compute the mass of a 3D-printed part captured as a binary STL scan whose per-triangle Attribute Byte Count word stores a Material ID. Filters out scanning debris by selecting the largest connected component, looks up density for the part's Material ID in a markdown table, and writes the result to a fixed-shape JSON report. Use when the task involves a binary STL with embedded Material IDs, a density lookup table, and a mass_report.json output — particularly the `/root/scan_data.stl` + `/root/material_density_table.md` → `/root/mass_report.json` flow.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.11+ (standard library only). Designed for tasks where the STL lives at /root/scan_data.stl.
---

```yaml
purpose: >
  Compute the mass of the main 3D-printed part in a binary STL scan whose
  triangles carry a Material ID in the otherwise-unused 2-byte Attribute
  Byte Count. The scan may include debris; the main part is the largest
  connected component. Density comes from a markdown lookup table keyed
  by Material ID. Output is a fixed-shape JSON report. Tolerance on the
  reported mass is 0.1%, which makes correct unit handling load-bearing.

trigger_when:
  - The task names `/root/scan_data.stl` and `/root/material_density_table.md` as inputs.
  - The expected output is `/root/mass_report.json` with `main_part_mass` and `material_id` fields.
  - A binary STL is described as having per-triangle Material IDs in its Attribute Byte Count word.
  - A 3D-scan task asks for mass of the largest part after filtering out debris.

do_not_use_when:
  - The STL is ASCII, not binary (ASCII STL has no attribute-byte-count field).
  - The "Material ID" lives somewhere other than the attribute byte count (e.g. file metadata).
  - The task asks for surface area, dimensions, or a non-mass property.

scope_and_approval: >
  Read-only on `/root/scan_data.stl` and `/root/material_density_table.md`.
  Writes only `/root/mass_report.json` (or the path passed via `--output`).
  No network, no destructive operations. Safe to run without prompting.

steps:
  - name: inspect-inputs
    description: >
      Read the first ~40 lines of `/root/material_density_table.md` to see the
      column layout and the density unit string (e.g. `g/cm^3`, `kg/m^3`).
      Confirm `/root/scan_data.stl` exists and that its size satisfies
      `size == 84 + 50 * N` for some integer `N` (this is the binary-STL
      invariant; failure means the file is ASCII STL or corrupted).

  - name: run-script
    description: >
      Run `scripts/compute_mass.py --verbose` with the defaults. The script
      parses the STL, runs union-find on shared vertices to isolate the
      largest connected component, takes the mode Material ID across that
      component's triangles, computes volume via the signed-tetrahedron sum,
      auto-detects the density unit from the markdown table, converts to a
      common base (g/mm^3), and writes the JSON report. `--verbose` prints
      triangle counts per component, the chosen Material ID with its
      dominance ratio, raw volume, density value+unit, and the final mass.

  - name: verify-assumptions
    description: >
      Confirm the script's reported unit assumptions match the data before
      accepting the result. The defaults assume STL units are millimeters
      and mass is grams; density unit is auto-detected. If the density
      table uses an unusual unit string the auto-detector misses, re-run
      with `--density-unit` set explicitly. If the part appears too large
      or too small (e.g. dimensions in cm or inches), re-run with
      `--stl-unit cm` or `--stl-unit in`.

  - name: sanity-check-output
    description: >
      Read `/root/mass_report.json` and confirm exactly two keys
      (`main_part_mass`, `material_id`), with `material_id` an integer and
      `main_part_mass` a positive float. Cross-check `main_part_mass`
      against a back-of-envelope: `volume * density` from the verbose log,
      then unit-corrected to the chosen mass unit.

decisions:
  - signal: Verbose log reports one giant component (>95% of triangles) and a few tiny ones.
    action: Expected. The giant component is the part; tiny components are debris. Proceed.
  - signal: Verbose log reports a near-even split (e.g. 50/50) across two components.
    action: >
      Suspicious. Confirm the largest is actually the printed part by checking
      its Material ID against plausible entries in the density table. If unsure,
      report the ambiguity rather than silently picking one.
  - signal: Material ID dominance is well below 100% (e.g. 800/1000 triangles).
    action: >
      The component may include stray triangles with mismatched IDs. The script
      already takes the mode; this is the right call. Note the dominance ratio
      in your summary.
  - signal: Density unit auto-detection fails (script exits with "density unit not detected").
    action: >
      Re-run with `--density-unit` set explicitly. Inspect the table to pick
      between `g/cm^3`, `kg/m^3`, or `g/mm^3`. Do not guess — read the table.
  - signal: Density lookup raises `LookupError` for the chosen Material ID.
    action: >
      Either the wrong component was selected or the table is incomplete.
      Re-run with `--verbose` and inspect the second-largest component's
      dominant Material ID; if that one is in the table, the largest may be
      debris (rare — only happens when debris outweighs the part).
  - signal: STL file size is not exactly `84 + 50 * N`.
    action: >
      File is not a clean binary STL. Inspect the first 80 bytes — if it
      starts with `solid `, it may be ASCII STL despite the `.stl` extension,
      and this skill does not apply.

modes:
  - name: default
    body: >
      `uv run scripts/compute_mass.py --verbose` (or plain `python3
      scripts/compute_mass.py --verbose`). Writes the report to
      `/root/mass_report.json`.
  - name: dry-run
    body: >
      Add `--dry-run` to print the JSON to stdout without touching
      `/root/mass_report.json`. Use when iterating on unit assumptions.
  - name: alternative-units
    body: >
      Override units when defaults are wrong:
      `--stl-unit {mm,cm,m,in}`, `--density-unit {g/cm^3,kg/m^3,g/mm^3}`,
      `--mass-unit {g,kg}`.

anti_patterns:
  - Trusting `triangles[0]`'s Material ID for the whole component. Take the mode across the component; the file may contain stray mismatched words.
  - Computing volume over **all** triangles instead of just the largest component. Debris will inflate the result.
  - Computing volume from a non-watertight subset. The signed-tetrahedron formula assumes a closed mesh; sums over open meshes are meaningless.
  - Centering the mesh before summing. The signed-tetrahedron formula already handles arbitrary origins; centering is unnecessary and adds floating-point error.
  - Assuming density is `g/cm^3` without checking the table. Many tables use `kg/m^3` — the numeric value differs by 1000.
  - Skipping vertex quantization in connected-component detection. Floating-point jitter on shared vertices will fragment one component into many.
  - Writing extra keys into `mass_report.json` (e.g. `volume`, `density`). The expected schema is exactly two keys.
  - Rounding aggressively before writing. 0.1% tolerance means keep at least 4 significant figures.

scenarios:
  - need: Standard task invocation — binary STL with embedded Material IDs at `/root/scan_data.stl`.
    context: Density table at `/root/material_density_table.md` uses a markdown table with columns `| ID | Material | Density (g/cm^3) |`.
    action: >
      Run `scripts/compute_mass.py --verbose`. Verbose log shows 1 large
      component (12480 triangles) and 6 debris components (3-18 triangles
      each). Material ID 42 wins 12480/12480. Density 1.24 g/cm^3 detected.
      Volume 9847.3 mm^3 → mass 12.21 g.
    outcome: >
      `/root/mass_report.json` contains
      `{"main_part_mass": 12.21..., "material_id": 42}`. Within 0.1%.

  - need: Density table uses kg/m^3.
    context: Header reads "Density (kg/m^3)" and entries are like `1240`.
    action: >
      Auto-detection picks `kg/m^3`. Script converts internally
      (1240 kg/m^3 = 1.24e-3 g/mm^3). No flag override needed.
    outcome: Same numeric mass as the g/cm^3 case; verify in the verbose log.

  - need: Auto-detection of density unit fails because the table writes "g per cubic cm" in prose.
    context: Script exits with code 2 and "density unit not detected".
    action: Re-read the table to confirm intent, then re-run with `--density-unit g/cm^3`.
    outcome: Mass computed correctly; report written.
```
