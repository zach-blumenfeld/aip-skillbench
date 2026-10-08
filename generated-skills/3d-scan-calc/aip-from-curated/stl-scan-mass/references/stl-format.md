# Binary STL and scan-cleanup notes

Load when a file fails to parse, the material ID looks wrong, or you need to inspect the
mesh by hand.

## Binary layout (little-endian)

| Offset | Size | Content |
|---|---|---|
| 0 | 80 | Header text (free-form; may begin with "solid" even in binary files) |
| 80 | 4 | uint32 triangle count N |
| 84 + 50·i | 12 | float32 normal (nx, ny, nz) — ignored, often zero in scans |
| +12 | 36 | float32 vertices v1, v2, v3 (x, y, z each) |
| +48 | 2 | uint16 attribute byte count — used here as the **material ID** (elsewhere: color) |

A file is binary iff `84 + 50·N == file size`. ASCII STL (`solid … facet normal … vertex …
endfacet … endsolid`) has no attribute field, so it carries no material ID.

## Volume

Signed tetrahedron sum: V = |Σ v1·(v2×v3)| / 6 over a component's triangles. Exact for a
closed, consistently wound shell, in the STL coordinate unit cubed. Do not assume mm or
inches: the unit comes from the task (e.g. cm coordinates → cm³). Open edges or flipped
triangles make the result unreliable.

## Components

Triangles sharing a vertex (coordinates rounded to 5 decimals) belong to one component.
Scan debris shows up as small separate components, often with a "debris"/noise material
ID. The main part is the component with the largest enclosed volume, not the one with the
most triangles and not the sum of all components.

## By hand

```bash
cd <skill>/scripts && python3 mesh_tool.py /path/to/file.stl   # {'main_part_volume', 'main_part_material_id', 'total_components'}
```
```python
import sys; sys.path.append("<skill>/scripts")
from mesh_tool import MeshAnalyzer
a = MeshAnalyzer("/path/to/file.stl")
a.component_report()   # per component: volume, triangles, material_id, attribute_histogram, open_edges, bbox
```
