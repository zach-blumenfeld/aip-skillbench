# Report the mass

Result for `{stl_path}`:

- Mass: {mass} {mass_unit}
- Material: ID {material_id_used} ({material_name}), density {density} {density_unit}
- Volume: {main_part_volume} STL units³ → {volume_in_density_units} in density units
  (coordinate unit {coordinate_unit_used}, factor {volume_conversion_factor})
- Components in scan: {total_components} (only the largest was used)
- Notes: {mass_notes}; reviewed issues: {mass_issues}

Deliver the answer exactly as the task instructions ask: the file path, file format
(JSON keys, CSV columns, plain text), key names, units, and rounding they specify. If
they ask for a different mass unit than {mass_unit}, convert (1 kg = 1000 g,
1 lb = 453.59237 g). Do not round unless asked; if asked, round only the final value.
If the task asks for volume, material ID, or component count too, take them from the
state above. Re-open the written file to confirm it parses and holds the right numbers.

Return a JSON object with only the new keys: `answer_location` (the path written, or
"chat"), `reported_mass` (the number exactly as reported), and `reported_unit` (its unit).
Everything else is already in the state.
