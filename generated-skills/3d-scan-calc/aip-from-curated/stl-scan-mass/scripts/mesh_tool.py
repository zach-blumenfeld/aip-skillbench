"""STL mesh analysis: parsing, connected components, volume, attribute (material ID) extraction.

Adapted from source/mesh-analysis/scripts/mesh_tool.py. Pure standard library (the task
container ships bare python3, no numpy). Same public API as the original
(MeshAnalyzer(path).analyze_largest_component()), plus a per-component report.

Changes vs. the original, and why:
- Binary/ASCII detection: binary when 84 + 50*count == file size (the original's rule);
  otherwise ASCII. Binary files may legally start with "solid", so the header text is not
  used to decide.
- Parse warnings go to self.warnings / stderr, never stdout (stdout must stay pure JSON
  when called from an AIP execution step).
- Material ID of a component = most common NON-ZERO attribute across its triangles
  (0 when every triangle is 0). The original took the first triangle's attribute, which
  is wrong whenever the component mixes an unset 0 attribute with the real ID.
- Components are found with union-find over shared (quantized) vertices; same
  connectivity rule as the original BFS (triangles sharing a vertex rounded to 5
  decimals are connected), but linear time on large scans.
"""

import collections
import os
import struct
import sys


class MeshAnalyzer:
    def __init__(self, filepath):
        self.filepath = filepath
        # Triangles as tuples: (v1, v2, v3, attr)
        self.triangles = []
        self.format = None
        self.header = ""
        self.warnings = []
        self._parse()

    # ---------------------------------------------------------------- parsing
    def _parse(self):
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"{self.filepath} not found.")
        try:
            self._parse_binary()
            self.format = "binary"
        except Exception as e:
            self.warnings.append(f"Binary parse failed ({e}); parsed as ASCII STL, material IDs unavailable (all 0).")
            self.triangles = []
            self._parse_ascii()
            self.format = "ascii"

    def _parse_ascii(self):
        current = []
        with open(self.filepath, errors="replace") as f:
            for line in f:
                parts = line.strip().split()
                if not parts:
                    continue
                if parts[0] == "solid" and not self.header:
                    self.header = " ".join(parts[1:])
                elif parts[0] == "vertex":
                    current.append((float(parts[1]), float(parts[2]), float(parts[3])))
                elif parts[0] == "endfacet":
                    if len(current) == 3:
                        self.triangles.append((current[0], current[1], current[2], 0))
                    current = []

    def _parse_binary(self):
        file_size = os.path.getsize(self.filepath)
        with open(self.filepath, "rb") as f:
            header = f.read(80)
            count_data = f.read(4)
            if len(count_data) < 4:
                raise ValueError("file shorter than 84-byte binary header")
            count = struct.unpack("<I", count_data)[0]
            expected = 84 + 50 * count
            if file_size != expected:
                raise ValueError(f"size mismatch: header says {count} triangles -> {expected} bytes, file is {file_size}")
            self.header = header.rstrip(b"\x00 ").decode("ascii", errors="replace")
            data = f.read(50 * count)
        unpack = struct.Struct("<12fH").unpack_from
        tris = self.triangles
        for i in range(count):
            v = unpack(data, 50 * i)
            # v[0:3] is the facet normal (ignored; often zero or wrong in scans)
            tris.append(((v[3], v[4], v[5]), (v[6], v[7], v[8]), (v[9], v[10], v[11]), v[12]))

    # ---------------------------------------------------------------- geometry
    @staticmethod
    def signed_volume(triangles):
        total = 0.0
        for v1, v2, v3, _ in triangles:
            cp_x = v2[1] * v3[2] - v2[2] * v3[1]
            cp_y = v2[2] * v3[0] - v2[0] * v3[2]
            cp_z = v2[0] * v3[1] - v2[1] * v3[0]
            total += v1[0] * cp_x + v1[1] * cp_y + v1[2] * cp_z
        return total / 6.0

    def get_volume(self, triangles=None):
        tris = triangles if triangles is not None else self.triangles
        return abs(self.signed_volume(tris))

    def get_components(self):
        def quantize(v):
            return (round(v[0], 5), round(v[1], 5), round(v[2], 5))

        n = len(self.triangles)
        parent = list(range(n))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        first_owner = {}
        for i, t in enumerate(self.triangles):
            for v in t[:3]:
                q = quantize(v)
                j = first_owner.setdefault(q, i)
                if j != i:
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[ri] = rj
        groups = collections.OrderedDict()
        for i in range(n):
            groups.setdefault(find(i), []).append(self.triangles[i])
        return list(groups.values())

    @staticmethod
    def open_edge_count(triangles):
        """Edges not shared by exactly two triangles (0 for a closed, manifold shell)."""
        def q(v):
            return (round(v[0], 5), round(v[1], 5), round(v[2], 5))

        edges = collections.Counter()
        for t in triangles:
            a, b, c = q(t[0]), q(t[1]), q(t[2])
            for e in ((a, b), (b, c), (c, a)):
                edges[tuple(sorted(e))] += 1
        return sum(1 for k in edges.values() if k != 2)

    @staticmethod
    def material_of(triangles):
        hist = collections.Counter(t[3] for t in triangles)
        nonzero = [(cnt, mid) for mid, cnt in hist.items() if mid != 0]
        mat = max(nonzero)[1] if nonzero else 0
        return mat, dict(sorted(hist.items()))

    # ---------------------------------------------------------------- reports
    def component_report(self):
        comps = []
        for c in self.get_components():
            sv = self.signed_volume(c)
            mat, hist = self.material_of(c)
            xs = [p[0] for t in c for p in t[:3]]
            ys = [p[1] for t in c for p in t[:3]]
            zs = [p[2] for t in c for p in t[:3]]
            comps.append({
                "volume": abs(sv),
                "triangles": len(c),
                "material_id": mat,
                "attribute_histogram": {str(k): v for k, v in hist.items()},
                "open_edges": self.open_edge_count(c),
                "bbox_min": [min(xs), min(ys), min(zs)],
                "bbox_max": [max(xs), max(ys), max(zs)],
            })
        comps.sort(key=lambda r: r["volume"], reverse=True)
        return comps

    def analyze_largest_component(self):
        comps = self.component_report()
        if not comps:
            return {"main_part_volume": 0.0, "main_part_material_id": 0, "total_components": 0}
        return {
            "main_part_volume": comps[0]["volume"],
            "main_part_material_id": comps[0]["material_id"],
            "total_components": len(comps),
        }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        analyzer = MeshAnalyzer(sys.argv[1])
        for w in analyzer.warnings:
            print(w, file=sys.stderr)
        print(analyzer.analyze_largest_component())
