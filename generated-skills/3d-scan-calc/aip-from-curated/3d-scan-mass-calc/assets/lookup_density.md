# Density lookup for material ID {main_part_material_id}

The mesh analyzer identified the main part's material ID as
**{main_part_material_id}** (from the binary STL attribute bytes). Open the
density table at:

    {density_table_path}

Find the row whose material ID equals `{main_part_material_id}` (match the
integer, not a stringified form). Read off its density and the density's unit.

Normalize to **grams per cubic centimeter (g/cm³)** — see
`references/units-and-density.md` for conversions — and emit JSON matching the
next step's `inputs`:

```json
{{"density_g_per_cm3": <float>}}
```

Rules:
- Do not guess a density if the ID is not in the table. Stop and surface the
  problem.
- Do not change the material_id or volume — those pass through untouched.
- Keep the full precision from the table; the compute-mass step rounds nothing.
