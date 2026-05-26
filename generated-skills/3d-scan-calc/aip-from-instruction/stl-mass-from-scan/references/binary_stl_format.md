# Binary STL format — and the Material ID repurposing

## Standard binary STL layout

Little-endian throughout.

| Offset      | Size                  | Field                                              |
|-------------|-----------------------|----------------------------------------------------|
| `0`         | 80 bytes              | Header (free text; **must not** start with `solid` for binary detection) |
| `80`        | 4 bytes (`uint32`)    | Triangle count `N`                                 |
| `84 + 50k`  | 12 bytes (`3 × float32`) | Triangle `k` normal vector (often zeroed)       |
| `+12`       | 12 bytes (`3 × float32`) | Vertex 0 `(x, y, z)`                            |
| `+24`       | 12 bytes (`3 × float32`) | Vertex 1                                        |
| `+36`       | 12 bytes (`3 × float32`) | Vertex 2                                        |
| `+48`       | 2 bytes (`uint16`)    | **Attribute Byte Count** (normally `0`; here: **Material ID**) |

Per-triangle record is exactly 50 bytes. Total file size is `84 + 50·N` bytes.

## The Material ID hack (task-specific)

The standard says the trailing 2-byte word is the "attribute byte count" and
should be zero. In this task the scanner repurposes it to carry an
**unsigned 16-bit Material ID** per triangle. Read it with
`struct.unpack_from("<H", data, offset + 48)`.

Every triangle in the same connected component should carry the **same**
Material ID. Take the mode across the main component's triangles rather
than trusting one record — the file may contain stray mismatched words.

## Closed-mesh volume

For a watertight triangle mesh whose triangles are consistently oriented
(outward normals), the enclosed volume equals the absolute value of the
signed tetrahedron sum:

```
V = (1/6) * | Σ  v0 · (v1 × v2) |
            tris
```

This formula does not require centering on the origin; each triangle
contributes the signed volume of the tetrahedron `(origin, v0, v1, v2)`,
and the inside-vs-outside cancellation gives the enclosed volume.

If the mesh is not closed, the sum is meaningless. Closedness is implied
when each edge is shared by exactly two triangles in the same component.

## Connected components

Two triangles belong to the same component when they share at least one
vertex (in practice: at least one edge, but shared-vertex detection is
faster and sufficient when debris is well separated). Use union-find:

1. Quantize each vertex coordinate to a small bucket (e.g. `round(x / 1e-5)`)
   so floating-point jitter on shared vertices hashes to the same key.
2. Walk every triangle; for each of its three vertices, look up the
   bucket. If another triangle already claimed it, union the two
   triangles. Otherwise record this triangle as the bucket's owner.
3. Group by `find(i)` root and pick the largest set.

## Why the largest component is the "main part"

Scanner debris (loose triangles, dust, secondary surfaces) shows up as
small disconnected components. The actual printed part is one large
watertight shell — the largest connected component by triangle count is
the correct selection. Do not filter by Material ID at this stage; the
debris may share an ID with the part or have its own.
