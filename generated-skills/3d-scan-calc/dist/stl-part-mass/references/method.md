# Method details and fallbacks

Load when `selection_ok` is false or the script's numbers look wrong.

## Binary STL layout
- 80-byte header (ignored; may start with "solid" even for binary files — the size check decides).
- uint32 little-endian triangle count.
- Per triangle, 50 bytes: normal (3×float32), v1, v2, v3 (3×float32 each), uint16 attribute.
  The attribute is the "Attribute Byte Count" slot, reused here for the Material ID.
- Valid binary iff file size == 84 + 50·count.

## Connected components
Triangles sharing any vertex (coordinates rounded to 5 decimals) are in the same component.
If a scan has tiny seams (vertices off by >1e-5) the main part may split into pieces: the
analyze listing then shows several large components with the same Material ID and adjacent
bounding boxes. Sum them only if together they form the closed part (edge check on the union).

## Volume
Signed volume = Σ v1·(v2×v3) / 6 (divergence theorem); valid only for a closed, consistently
oriented shell (every directed edge has exactly one reversed partner). Outward winding gives a
positive sign; the script reports |signed|. Internal cavities appear as separate inward-facing
shells (opposite sign) inside the main bounding box.

## Choosing the main part
Default: largest |volume|. If largest-by-volume disagrees with largest-by-triangle-count, or
the main part is open, inspect the listing: the real part normally has the non-debris Material
ID from the density table, the most triangles, and a closed shell. A non-closed part's volume
cannot be trusted; report it as such rather than guessing.

## Units
Mass = Volume × scale × Density, scale = (STL length unit / density length unit)³:
mm→cm 0.001, m→cm 1e6, inch→cm 16.387064, same/unstated 1.
