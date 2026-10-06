# Units and density-table parsing

The mesh analyzer returns volume in **the cube of the STL coordinate unit**. The
STL file itself does not carry a unit; the task instructions do. Common choices:

| Unit | Linear factor to cm | Volume factor to cm³ |
|------|---------------------|----------------------|
| mm   | 0.1                 | 0.001                |
| cm   | 1.0                 | 1.0                  |
| m    | 100.0               | 1 000 000.0          |
| in   | 2.54                | 16.387064            |

If the task says "coordinates are in millimeters", pass `stl_coord_unit: "mm"`.

## Reading the density table

Density tables in these tasks are markdown. Shape varies, but each row maps a
numeric material ID to a density. The lookup step must:

1. Open `density_table_path` and read it.
2. Find the row whose material ID equals `main_part_material_id` (match on the
   integer, not the string — IDs like `0` or `42` show up unquoted).
3. Pull the density value and its stated unit from that row.
4. Normalize to **grams per cubic centimeter (g/cm³)** and emit that as
   `density_g_per_cm3`:
   - g/cm³ → use as-is
   - kg/m³ → divide by 1000  (1 kg/m³ = 0.001 g/cm³)
   - g/mm³ → multiply by 1000
   - lb/in³ → multiply by 27.6799

If the material ID is not in the table, stop and raise the problem; do not guess
a density. If the table lists multiple candidate materials for one ID, prefer
the row whose name matches any hint in the task instructions, otherwise take
the first and note the ambiguity.
