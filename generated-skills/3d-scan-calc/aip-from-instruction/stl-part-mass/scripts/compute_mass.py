#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Compute the mass of the main part in a binary STL whose per-triangle
"Attribute Byte Count" field stores a Material ID.

Pipeline (all deterministic; this script is the source of truth):
  1. Parse the binary STL (80-byte header, uint32 triangle count, then
     N x 50-byte triangle records: normal[3], v1[3], v2[3], v3[3] as
     float32 LE, then a uint16 LE attribute = Material ID).
  2. Group triangles into connected components by shared vertices and keep
     the LARGEST (the main part); everything else is scanning debris.
  3. Compute the enclosed volume of the main component via the signed-
     tetrahedron (divergence) sum, taken absolute.
  4. Read the Material ID from the main component (most common attribute).
  5. Look up the density for that Material ID in the markdown density table.
  6. Convert volume to match the density's length unit (STL coords assumed
     mm by default; override with --coord-unit) and compute mass = V * rho.
  7. Write {"main_part_mass": <float>, "material_id": <int>} to --out.

Pure standard library; no third-party deps. Run with `uv run` or `python3`.

Diagnostics (triangle counts, component sizes, parsed density, detected
units, conversion factor) print to STDERR so the result on STDOUT/in --out
stays clean and the unit reasoning is auditable.
"""

import argparse
import json
import re
import struct
import sys
from collections import Counter


# ---------------------------------------------------------------------------
# Binary STL parsing
# ---------------------------------------------------------------------------

HEADER_BYTES = 80
COUNT_BYTES = 4
RECORD_BYTES = 50  # 12 float32 (48) + 1 uint16 (2)
RECORD_FMT = "<12fH"  # little-endian: 12 floats then 1 unsigned short


def parse_binary_stl(path):
    """Return (triangles, attributes).

    triangles: list of (v1, v2, v3), each vertex a (x, y, z) float tuple.
    attributes: list of int (the uint16 attribute / Material ID per triangle).
    """
    with open(path, "rb") as fh:
        data = fh.read()

    if len(data) < HEADER_BYTES + COUNT_BYTES:
        raise ValueError(f"File too small to be a binary STL: {len(data)} bytes")

    # Reject ASCII STL (starts with "solid " and is not a valid binary record).
    if data[:5].lower() == b"solid":
        declared = struct.unpack_from("<I", data, HEADER_BYTES)[0]
        expected = HEADER_BYTES + COUNT_BYTES + declared * RECORD_BYTES
        if expected != len(data):
            raise ValueError(
                "File looks like ASCII STL, not binary. This skill handles "
                "binary STL only (Material ID is stored in the binary "
                "attribute-byte field)."
            )

    n = struct.unpack_from("<I", data, HEADER_BYTES)[0]
    body_start = HEADER_BYTES + COUNT_BYTES
    expected_len = body_start + n * RECORD_BYTES
    if len(data) < expected_len:
        raise ValueError(
            f"Declared {n} triangles need {expected_len} bytes but file is "
            f"{len(data)} bytes. Corrupt or truncated STL."
        )

    triangles = []
    attributes = []
    block = data[body_start:body_start + n * RECORD_BYTES]
    for rec in struct.iter_unpack(RECORD_FMT, block):
        # rec = (nx, ny, nz, x1, y1, z1, x2, y2, z2, x3, y3, z3, attr)
        v1 = (rec[3], rec[4], rec[5])
        v2 = (rec[6], rec[7], rec[8])
        v3 = (rec[9], rec[10], rec[11])
        triangles.append((v1, v2, v3))
        attributes.append(rec[12])
    return triangles, attributes


# ---------------------------------------------------------------------------
# Connected components by shared vertices (union-find)
# ---------------------------------------------------------------------------

def _quantize_factor(triangles):
    """A length scale for snapping near-identical vertices to the same key.

    Binary STL stores each triangle's vertices independently, so shared
    vertices usually have identical float32 bits; quantization only guards
    against tiny numeric noise. Use a tolerance relative to the bounding-box
    diagonal so it works regardless of model scale or units.
    """
    minc = [float("inf")] * 3
    maxc = [float("-inf")] * 3
    for tri in triangles:
        for v in tri:
            for i in range(3):
                if v[i] < minc[i]:
                    minc[i] = v[i]
                if v[i] > maxc[i]:
                    maxc[i] = v[i]
    diag = sum((maxc[i] - minc[i]) ** 2 for i in range(3)) ** 0.5
    tol = diag * 1e-6
    if not tol or tol <= 0:
        tol = 1e-9
    return tol


def _vkey(v, tol):
    return (round(v[0] / tol), round(v[1] / tol), round(v[2] / tol))


def find_components(triangles):
    """Union-find over triangles that share a vertex.

    Returns parent array (find() resolves each triangle to its component
    root). Triangles sharing at least one (quantized) vertex are unioned.
    """
    n = len(triangles)
    parent = list(range(n))

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    tol = _quantize_factor(triangles)
    vert_owner = {}  # quantized vertex key -> first triangle index seen
    for i, tri in enumerate(triangles):
        for v in tri:
            k = _vkey(v, tol)
            owner = vert_owner.get(k)
            if owner is None:
                vert_owner[k] = i
            else:
                union(i, owner)
    return parent, find


def largest_component(triangles):
    """Return the list of triangle indices in the largest connected component."""
    if not triangles:
        raise ValueError("STL contains no triangles")
    parent, find = find_components(triangles)
    members = {}
    for i in range(len(triangles)):
        members.setdefault(find(i), []).append(i)
    sizes = {root: len(idx) for root, idx in members.items()}
    biggest = max(sizes, key=sizes.get)
    return members[biggest], sizes


# ---------------------------------------------------------------------------
# Volume via signed tetrahedron sum (divergence theorem)
# ---------------------------------------------------------------------------

def mesh_volume(triangles, indices):
    """Absolute enclosed volume of the closed surface formed by `indices`.

    Sum of signed tetra volumes (a . (b x c)) / 6 over each triangle, in the
    native cubic units of the coordinates. Accumulated in float64 (Python
    float) for accuracy.
    """
    total = 0.0
    for i in indices:
        a, b, c = triangles[i]
        cx = b[1] * c[2] - b[2] * c[1]
        cy = b[2] * c[0] - b[0] * c[2]
        cz = b[0] * c[1] - b[1] * c[0]
        total += (a[0] * cx + a[1] * cy + a[2] * cz)
    return abs(total) / 6.0


# ---------------------------------------------------------------------------
# Density table parsing (markdown)
# ---------------------------------------------------------------------------

_NUM = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def parse_density_table(path):
    """Parse a markdown density table into {material_id: density_float}.

    Robust to column order and extra columns. Finds a pipe table, locates the
    'id' column and the 'density' column by header keyword, and extracts the
    first integer / first float from those cells. Also returns the raw header
    text of the density column so units can be detected downstream.
    """
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()

    rows = [ln.strip() for ln in lines if ln.count("|") >= 2]
    if len(rows) < 2:
        raise ValueError(
            "No markdown table with >=2 pipe-delimited rows found in density "
            "table. Inspect the file and pass values manually if needed."
        )

    def cells(line):
        parts = line.strip().strip("|").split("|")
        return [p.strip() for p in parts]

    header = cells(rows[0])
    # Skip the separator row (---|---) if present.
    data_rows = rows[1:]
    if data_rows and set(data_rows[0].replace("|", "").replace(" ", "")) <= set("-:"):
        data_rows = data_rows[1:]

    id_col = density_col = None
    for idx, h in enumerate(header):
        hl = h.lower()
        if id_col is None and ("id" in hl or "material" in hl):
            id_col = idx
        if density_col is None and "densit" in hl:
            density_col = idx
    if id_col is None:
        id_col = 0
    if density_col is None:
        density_col = 1 if len(header) > 1 else 0

    density_header = header[density_col]
    table = {}
    for r in data_rows:
        c = cells(r)
        if len(c) <= max(id_col, density_col):
            continue
        id_m = re.search(r"\d+", c[id_col])
        den_m = _NUM.search(c[density_col])
        if not id_m or not den_m:
            continue
        table[int(id_m.group())] = float(den_m.group())
    if not table:
        raise ValueError(
            "Parsed the markdown table but extracted no (id, density) pairs. "
            "Header was: " + " | ".join(header)
        )
    return table, density_header


# ---------------------------------------------------------------------------
# Unit handling
# ---------------------------------------------------------------------------

# length unit -> meters
_LEN_M = {"mm": 1e-3, "cm": 1e-2, "m": 1.0, "um": 1e-6, "in": 0.0254}


def detect_density_length_unit(density_header):
    """Find the length unit in a density column header like 'Density (g/cm^3)'.

    Returns one of 'mm','cm','m','um','in' or None if undetectable.
    """
    h = density_header.lower()
    # Order matters: check 'mm'/'cm'/'um' before bare 'm'.
    for tok in ("mm", "cm", "um", "in", "m"):
        # require it to look like a per-length denominator, e.g. /cm, cm^3, cm3
        if re.search(r"[/·*]?\s*" + tok + r"\s*\^?\s*3", h) or re.search(r"/\s*" + tok + r"\b", h):
            return tok
    return None


def volume_conversion_factor(coord_unit, density_len_unit):
    """Factor to multiply a volume expressed in coord_unit^3 to get it in
    density_len_unit^3. Returns 1.0 when either unit is unknown (no conversion).
    """
    if not density_len_unit or coord_unit not in _LEN_M or density_len_unit not in _LEN_M:
        return 1.0
    ratio = _LEN_M[coord_unit] / _LEN_M[density_len_unit]
    return ratio ** 3


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stl", default="/root/scan_data.stl")
    ap.add_argument("--density-table", default="/root/material_density_table.md")
    ap.add_argument("--out", default="/root/mass_report.json")
    ap.add_argument(
        "--coord-unit", default="mm",
        help="Length unit of STL coordinates (mm|cm|m|um|in). STL is "
             "conventionally mm. Default: mm.",
    )
    ap.add_argument(
        "--density-unit", default=None,
        help="Override length unit in the density (e.g. cm for g/cm^3). "
             "By default it is auto-detected from the table header.",
    )
    ap.add_argument(
        "--no-unit-convert", action="store_true",
        help="Multiply volume*density with NO unit conversion (use when "
             "coordinate and density units already match).",
    )
    args = ap.parse_args()

    triangles, attributes = parse_binary_stl(args.stl)
    print(f"[stl] {len(triangles)} triangles parsed", file=sys.stderr)

    main_idx, sizes = largest_component(triangles)
    print(
        f"[components] {len(sizes)} component(s); largest has "
        f"{len(main_idx)} triangles (sizes: "
        f"{sorted(sizes.values(), reverse=True)[:10]})",
        file=sys.stderr,
    )

    volume = mesh_volume(triangles, main_idx)
    print(f"[volume] main-part volume = {volume:.6f} ({args.coord_unit}^3)",
          file=sys.stderr)

    main_attrs = [attributes[i] for i in main_idx]
    material_id = Counter(main_attrs).most_common(1)[0][0]
    print(f"[material] Material ID = {material_id} "
          f"(distinct in main part: {sorted(set(main_attrs))})", file=sys.stderr)

    table, density_header = parse_density_table(args.density_table)
    if material_id not in table:
        raise SystemExit(
            f"Material ID {material_id} not found in density table. "
            f"Available IDs: {sorted(table)}"
        )
    density = table[material_id]
    print(f"[density] rho = {density} (column header: '{density_header}')",
          file=sys.stderr)

    if args.no_unit_convert:
        factor = 1.0
        den_unit = None
    else:
        den_unit = args.density_unit or detect_density_length_unit(density_header)
        factor = volume_conversion_factor(args.coord_unit, den_unit)
    print(f"[units] coord={args.coord_unit} density_len={den_unit} "
          f"volume_factor={factor}", file=sys.stderr)

    mass = volume * factor * density
    print(f"[mass] main_part_mass = {mass}", file=sys.stderr)

    result = {"main_part_mass": mass, "material_id": int(material_id)}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh)
        fh.write("\n")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
