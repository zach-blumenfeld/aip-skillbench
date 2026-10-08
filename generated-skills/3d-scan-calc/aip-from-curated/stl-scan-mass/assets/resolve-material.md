# Resolve the flagged mass calculation

The deterministic mass calculation for `{stl_path}` stopped for review.

Issues: {mass_issues}
Notes: {mass_notes}

Main part (largest connected component by volume): volume {main_part_volume} (STL units³),
material ID {main_part_material_id}, attribute histogram {main_part_attribute_histogram},
open edges {main_part_open_edges}. Mesh has {total_components} components; the largest are:
{components}

Density table: `{density_table_path}`. Coordinate unit given: `{coordinate_unit}`.

Do this:

1. Re-read the task instructions for anything that settles the issue: the coordinate unit,
   which part is wanted, a material named in the prompt, a required output unit.
2. Open the density table and the component list above. Typical resolutions:
   - Material ID not in table / ID 0 / ASCII file: look at the main part's attribute
     histogram; a non-zero ID that is in the table is the material. If the file carries no
     usable ID, take the material the task names. Set `material_id_override` (a table ID).
   - The task explicitly names a material that differs from the file's ID: the task wins;
     set `material_id_override` and mention the conflict when reporting.
   - Mixed IDs on the main part: keep the dominant non-zero ID unless the task says otherwise.
   - Density unit unreadable: set `density_override` and `density_unit_override` (e.g. `g/cm3`).
   - Coordinate unit wrong or unknown: set `coordinate_unit` (mm, cm, m, in, ft) from the task.
   - Material labelled debris/noise, or the second component is nearly as large: check the
     component list; the main part is the largest closed body. If the ranking is right, accept.
   - Open edges: the shell-sum volume is still the best estimate available; accept unless
     the task gives another volume source.
3. Return JSON with only the overrides you set plus `"review_acknowledged": true` once
   every listed issue is either fixed or judged harmless; everything else is already in the
   state. Do not type in a mass yourself; compute-mass recomputes it.
