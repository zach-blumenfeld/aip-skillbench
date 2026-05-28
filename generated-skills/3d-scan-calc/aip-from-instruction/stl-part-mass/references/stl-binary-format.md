# Binary STL format, volume math, and unit notes

Load this when `compute_mass.py` errors, when output looks wrong, or when you
need to adapt the parsing / unit handling by hand.

## Binary STL byte layout

A binary STL file is laid out as:

| Offset      | Size            | Meaning                                   |
|-------------|-----------------|-------------------------------------------|
| 0           | 80 bytes        | Header (free text; ignore it)             |
| 80          | 4 bytes         | `uint32` little-endian — triangle count N |
| 84          | N × 50 bytes    | Triangle records                          |

Each 50-byte triangle record:

| Field            | Size     | Type                |
|------------------|----------|---------------------|
| normal           | 12 bytes | 3 × `float32` LE    |
| vertex 1         | 12 bytes | 3 × `float32` LE    |
| vertex 2         | 12 bytes | 3 × `float32` LE    |
| vertex 3         | 12 bytes | 3 × `float32` LE    |
| attribute count  | 2 bytes  | `uint16` LE         |

`struct` format string for one record: `"<12fH"` (48 + 2 = 50 bytes).

### The Material-ID trick

The 2-byte "Attribute Byte Count" is normally 0 and unused. In this task it is
repurposed to store the **Material ID** of the object. Read it as a little-
endian `uint16`. All triangles belonging to the same physical part carry the
same Material ID; take the most common value across the main component's
triangles (debris may carry different/garbage values).

ASCII STL (file begins with the text `solid `) has no binary attribute field
and cannot carry a Material ID this way — this task always supplies binary STL.

## Largest connected component (filtering debris)

Scanning debris shows up as small mesh islands disconnected from the main part.
Group triangles into connected components, then keep the largest by triangle
count.

- Two triangles are connected if they share a vertex. Binary STL stores each
  triangle's vertices independently, so "shared" means equal coordinates.
- Shared vertices from a clean export usually have identical `float32` bits.
  Quantize coordinates to a tolerance relative to the bounding-box diagonal
  (e.g. `diag * 1e-6`) to absorb tiny numeric noise before comparing.
- Union-find (disjoint set) over triangles sharing a quantized vertex is the
  simplest correct approach.

Compute the volume over **only** the main component's triangles so debris
volume never contaminates the result.

## Enclosed volume (signed-tetrahedron / divergence sum)

For a closed triangulated surface, the enclosed volume is the sum of signed
tetrahedron volumes formed by each triangle and the origin:

```
V = | Σ_triangles  a · (b × c) | / 6
```

where `a, b, c` are the triangle's three vertices. The sign of each term
depends on facet winding; summing then taking the absolute value yields the
correct volume regardless of where the origin sits, as long as the mesh is
closed. Accumulate in float64 (Python's `float`) for 0.1 %-level accuracy.

This volume is in the **cube of the coordinate unit** (e.g. mm³ if coordinates
are millimetres).

## Units — the most common source of a wrong answer

STL files are unitless by convention but almost always millimetres. Density
tables almost always quote **g/cm³**. Mixing them is a factor-of-1000 error per
power, so a raw `volume × density` is wrong by 1000× when coords are mm and
density is per cm³.

Convert the volume to the density's length unit before multiplying:

```
V_in_density_units³ = V_coord³ × (coord_len_in_m / density_len_in_m)³
mass = V_in_density_units³ × density
```

Length unit → metres: `mm=1e-3`, `cm=1e-2`, `m=1.0`, `µm=1e-6`, `in=0.0254`.

`compute_mass.py` auto-detects the density's length unit from the table's
column header (e.g. `Density (g/cm^3)` → `cm`) and assumes mm coordinates.
**Always read `material_density_table.md` yourself** to confirm the density
unit and check whether the task states a coordinate unit. Override with
`--coord-unit` / `--density-unit`, or pass `--no-unit-convert` when the units
already match. The mass is reported in the density's mass unit (grams for
g/cm³). Do not pre-round it — the grader allows 0.1 % tolerance, and rounding a
small mass to 2 decimals can blow past that.
