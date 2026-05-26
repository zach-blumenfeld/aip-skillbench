#!/usr/bin/env python3
"""Compute the mass of the main 3D-printed part in a scan-data binary STL.

The binary STL repurposes each triangle's 2-byte Attribute Byte Count as a
Material ID. The scan may include debris; the "main part" is the largest
connected component (by triangle count). Volume is the closed-mesh signed
tetrahedron sum. Density is looked up in a markdown table by Material ID.

Default I/O paths match the task:
    --stl              /root/scan_data.stl
    --density-table    /root/material_density_table.md
    --output           /root/mass_report.json

Unit handling:
- Volume is computed in (stl-unit)^3. Default --stl-unit mm.
- Density unit is auto-detected from the table header / cell suffix
  (e.g. "g/cm^3", "g/cc", "kg/m^3"). Override with --density-unit.
- Mass is emitted in --mass-unit (default g).

Run with --verbose to print component counts, volume, density, and units
so the caller can sanity-check assumptions before trusting the JSON.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from collections import Counter
from pathlib import Path


# ---------- Binary STL parsing ----------

STL_HEADER_BYTES = 80
STL_TRIANGLE_BYTES = 50  # 12 normal + 36 vertices + 2 attribute


def parse_binary_stl(path: Path):
    """Yield (v0, v1, v2, material_id) per triangle.

    v0/v1/v2 are 3-tuples of floats. material_id is the unsigned 16-bit
    "attribute byte count" word that the task repurposes as Material ID.
    """
    data = path.read_bytes()
    if len(data) < STL_HEADER_BYTES + 4:
        raise ValueError(f"{path}: file too short to be a binary STL")
    (tri_count,) = struct.unpack_from("<I", data, STL_HEADER_BYTES)
    expected = STL_HEADER_BYTES + 4 + tri_count * STL_TRIANGLE_BYTES
    if len(data) != expected:
        # Some writers pad; warn but proceed if at least enough bytes.
        if len(data) < expected:
            raise ValueError(
                f"{path}: declares {tri_count} triangles, needs {expected} bytes, has {len(data)}"
            )

    offset = STL_HEADER_BYTES + 4
    for _ in range(tri_count):
        # Skip the 12-byte normal; we'll use vertices directly.
        v = struct.unpack_from("<9f", data, offset + 12)
        material_id = struct.unpack_from("<H", data, offset + 48)[0]
        v0 = (v[0], v[1], v[2])
        v1 = (v[3], v[4], v[5])
        v2 = (v[6], v[7], v[8])
        yield v0, v1, v2, material_id
        offset += STL_TRIANGLE_BYTES


# ---------- Connected components via shared vertices ----------

# Quantize vertex coordinates so floating-point jitter on shared vertices
# still hashes to the same key. 1e-5 is tight enough for typical
# mm-scale prints (10 nm bucket); loosen with --quantize if needed.
DEFAULT_QUANTIZE = 1e-5


def _key(v, q: float):
    return (round(v[0] / q), round(v[1] / q), round(v[2] / q))


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def largest_component(triangles, quantize: float):
    """Return (indices_of_largest, components_count, component_sizes).

    indices_of_largest is a list of triangle indices in the largest component.
    """
    n = len(triangles)
    uf = UnionFind(n)
    vertex_to_tri: dict[tuple, int] = {}
    for i, (v0, v1, v2, _mid) in enumerate(triangles):
        for v in (v0, v1, v2):
            k = _key(v, quantize)
            prev = vertex_to_tri.get(k)
            if prev is None:
                vertex_to_tri[k] = i
            else:
                uf.union(prev, i)

    buckets: dict[int, list[int]] = {}
    for i in range(n):
        r = uf.find(i)
        buckets.setdefault(r, []).append(i)

    sizes = sorted((len(v) for v in buckets.values()), reverse=True)
    largest = max(buckets.values(), key=len)
    return largest, len(buckets), sizes


# ---------- Volume ----------

def signed_volume(triangles, indices) -> float:
    """Sum of signed tetrahedron volumes for a closed mesh.

    V = (1/6) * sum( v0 . (v1 x v2) ). Returns absolute value.
    """
    total = 0.0
    for i in indices:
        v0, v1, v2, _ = triangles[i]
        cx = v1[1] * v2[2] - v1[2] * v2[1]
        cy = v1[2] * v2[0] - v1[0] * v2[2]
        cz = v1[0] * v2[1] - v1[1] * v2[0]
        total += v0[0] * cx + v0[1] * cy + v0[2] * cz
    return abs(total) / 6.0


# ---------- Density table ----------

DENSITY_UNIT_PATTERNS = [
    # (regex, canonical key)
    (re.compile(r"\bg\s*/\s*cm\s*\^?\s*3\b", re.I), "g/cm^3"),
    (re.compile(r"\bg\s*/\s*cc\b", re.I), "g/cm^3"),
    (re.compile(r"\bg\s*/\s*ml\b", re.I), "g/cm^3"),
    (re.compile(r"\bkg\s*/\s*m\s*\^?\s*3\b", re.I), "kg/m^3"),
    (re.compile(r"\bg\s*/\s*mm\s*\^?\s*3\b", re.I), "g/mm^3"),
    (re.compile(r"\bkg\s*/\s*L\b", re.I), "g/cm^3"),  # 1 kg/L == 1 g/cm^3
]


def detect_density_unit(text: str) -> str | None:
    for pat, canon in DENSITY_UNIT_PATTERNS:
        if pat.search(text):
            return canon
    return None


# Match a markdown-table row like:  | 42 | PLA | 1.24 |
ROW_PATTERN = re.compile(r"^\s*\|(.+)\|\s*$")
# Match a key:value style line:  Material 42: 1.24 g/cm^3
KEYVAL_PATTERN = re.compile(r"(?:material(?:\s*id)?\s*)?(\d+)\s*[:=,|]\s*([^\s|]+)", re.I)


def parse_density_table(path: Path, material_id: int) -> tuple[float, str | None]:
    """Return (density_value, detected_unit_string_or_None).

    Tolerates several formats: markdown tables with a numeric ID column and
    a density column, or simple "id: density" lines. The density cell may
    embed a unit suffix (e.g. "1.24 g/cm^3").
    """
    text = path.read_text()
    table_unit = detect_density_unit(text)

    # Try markdown table parsing.
    rows = []
    for line in text.splitlines():
        m = ROW_PATTERN.match(line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        rows.append(cells)
    # Drop alignment row (e.g. |---|---|) and header row when present.
    rows = [r for r in rows if not all(set(c) <= set("-: ") for c in r)]
    for row in rows:
        # Look for the ID in any cell, density in another.
        id_cell = None
        for idx, cell in enumerate(row):
            if cell.isdigit() and int(cell) == material_id:
                id_cell = idx
                break
        if id_cell is None:
            continue
        for idx, cell in enumerate(row):
            if idx == id_cell:
                continue
            num = _extract_number(cell)
            if num is not None:
                cell_unit = detect_density_unit(cell) or table_unit
                return num, cell_unit

    # Fallback: key:value lines.
    for line in text.splitlines():
        m = KEYVAL_PATTERN.search(line)
        if not m:
            continue
        if int(m.group(1)) != material_id:
            continue
        num = _extract_number(m.group(2))
        if num is not None:
            return num, detect_density_unit(line) or table_unit

    raise LookupError(f"density for material_id={material_id} not found in {path}")


_NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _extract_number(s: str) -> float | None:
    m = _NUM_RE.search(s)
    return float(m.group(0)) if m else None


# ---------- Unit conversion ----------

# Length conversion to millimeters.
LEN_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4}

# Density expressed in grams per cubic millimeter.
DENSITY_TO_G_PER_MM3 = {
    "g/mm^3": 1.0,
    "g/cm^3": 1e-3,  # 1 g/cm^3 = 1e-3 g/mm^3
    "kg/m^3": 1e-6,  # 1 kg/m^3 = 1e-6 g/mm^3
}

MASS_FROM_G = {"g": 1.0, "kg": 1e-3}


def compute_mass(volume_in_stl_units: float, stl_unit: str, density_value: float,
                 density_unit: str, mass_unit: str) -> float:
    # Convert volume to mm^3.
    factor = LEN_TO_MM[stl_unit] ** 3
    volume_mm3 = volume_in_stl_units * factor
    # Convert density to g/mm^3.
    density_g_per_mm3 = density_value * DENSITY_TO_G_PER_MM3[density_unit]
    mass_g = volume_mm3 * density_g_per_mm3
    return mass_g * MASS_FROM_G[mass_unit]


# ---------- CLI ----------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--stl", default="/root/scan_data.stl", type=Path)
    p.add_argument("--density-table", default="/root/material_density_table.md", type=Path)
    p.add_argument("--output", default="/root/mass_report.json", type=Path)
    p.add_argument("--stl-unit", default="mm", choices=list(LEN_TO_MM))
    p.add_argument("--density-unit", default=None, choices=list(DENSITY_TO_G_PER_MM3),
                   help="Override auto-detected density unit.")
    p.add_argument("--mass-unit", default="g", choices=list(MASS_FROM_G))
    p.add_argument("--quantize", default=DEFAULT_QUANTIZE, type=float,
                   help="Vertex-coordinate bucket size for component detection.")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="Print result; do not write the JSON file.")
    args = p.parse_args(argv)

    triangles = list(parse_binary_stl(args.stl))
    if not triangles:
        print(f"error: {args.stl} contains zero triangles", file=sys.stderr)
        return 1

    largest_idx, n_components, sizes = largest_component(triangles, args.quantize)
    # The Material ID for the part is the dominant ID across its triangles.
    # We take the mode rather than triangles[0]'s value, in case the file
    # has a stray mismatched word in the main component.
    mid_counts = Counter(triangles[i][3] for i in largest_idx)
    material_id, mid_dominance = mid_counts.most_common(1)[0]

    volume = signed_volume(triangles, largest_idx)

    density_value, detected_unit = parse_density_table(args.density_table, material_id)
    density_unit = args.density_unit or detected_unit
    if density_unit is None:
        print(
            "error: density unit not detected in table and --density-unit not set; "
            "rerun with --density-unit g/cm^3 (or appropriate)",
            file=sys.stderr,
        )
        return 2

    mass = compute_mass(volume, args.stl_unit, density_value, density_unit, args.mass_unit)

    if args.verbose:
        print(f"triangles total       : {len(triangles)}", file=sys.stderr)
        print(f"connected components  : {n_components}  sizes={sizes[:5]}{'...' if len(sizes) > 5 else ''}", file=sys.stderr)
        print(f"largest component     : {len(largest_idx)} triangles", file=sys.stderr)
        print(f"material_id (dominant): {material_id}  ({mid_dominance}/{len(largest_idx)} triangles)", file=sys.stderr)
        print(f"volume                : {volume:.6f} {args.stl_unit}^3", file=sys.stderr)
        print(f"density               : {density_value} {density_unit}", file=sys.stderr)
        print(f"mass                  : {mass:.6f} {args.mass_unit}", file=sys.stderr)

    payload = {
        "main_part_mass": round(mass, 6),
        "material_id": int(material_id),
    }

    if args.dry_run:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {args.output}: material_id={material_id} mass={mass:.6f} {args.mass_unit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
