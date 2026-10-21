"""STL parsing, connected components, volume, and density-table lookup.

Adapted from source/mesh-analysis/scripts/mesh_tool.py (MeshAnalyzer). Standard
library only: the task container has python3 and pip but no numpy.
"""

import collections
import os
import re
import struct


class MeshAnalyzer:
    def __init__(self, filepath):
        self.filepath = filepath
        # Triangles as tuples: (v1, v2, v3, attr) where attr is the 2-byte
        # "Attribute Byte Count" field, here used as the Material ID.
        self.triangles = []
        self.format = None
        self.warnings = []
        self._parse()

    def _parse(self):
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"{self.filepath} not found.")
        size = os.path.getsize(self.filepath)
        with open(self.filepath, "rb") as f:
            head = f.read(84)
        if len(head) < 84:
            self._parse_ascii()
            return
        count = struct.unpack("<I", head[80:84])[0]
        expected = 84 + 50 * count
        # Binary is decided by the size check, not the header text: binary
        # headers may legally start with "solid".
        if size == expected:
            self._parse_binary(count)
            return
        self._parse_ascii()
        if self.triangles:
            self.warnings.append("not a size-consistent binary STL; parsed as ASCII (no material IDs, all 0)")
        elif count > 0 and size > expected:
            self.triangles = []
            self.warnings.append(f"{size - expected} trailing bytes after {count} binary triangles ignored")
            self._parse_binary(count)

    def _parse_binary(self, count):
        self.format = "binary"
        unpack = struct.Struct("<12fH").unpack_from
        with open(self.filepath, "rb") as f:
            f.seek(84)
            data = f.read(50 * count)
        for i in range(count):
            r = unpack(data, 50 * i)
            # r[0:3] is the facet normal (ignored); vertices follow.
            self.triangles.append(((r[3], r[4], r[5]), (r[6], r[7], r[8]), (r[9], r[10], r[11]), r[12]))

    def _parse_ascii(self):
        self.format = "ascii"
        current = []
        with open(self.filepath, errors="replace") as f:
            for line in f:
                parts = line.strip().split()
                if not parts:
                    continue
                if parts[0] == "vertex":
                    current.append((float(parts[1]), float(parts[2]), float(parts[3])))
                elif parts[0] == "endfacet":
                    if len(current) == 3:
                        self.triangles.append((current[0], current[1], current[2], 0))
                    current = []

    @staticmethod
    def signed_volume(tris):
        total = 0.0
        for v1, v2, v3, _ in tris:
            cp_x = v2[1] * v3[2] - v2[2] * v3[1]
            cp_y = v2[2] * v3[0] - v2[0] * v3[2]
            cp_z = v2[0] * v3[1] - v2[1] * v3[0]
            total += v1[0] * cp_x + v1[1] * cp_y + v1[2] * cp_z
        return total / 6.0

    def get_volume(self, triangles=None):
        tris = triangles if triangles is not None else self.triangles
        return abs(self.signed_volume(tris))

    def get_components(self):
        """Group triangles that share a vertex (coordinates rounded to 5 decimals)."""
        parent = list(range(len(self.triangles)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        first_owner = {}
        for i, t in enumerate(self.triangles):
            for v in t[:3]:
                q = (round(v[0], 5), round(v[1], 5), round(v[2], 5))
                j = first_owner.setdefault(q, i)
                if j != i:
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[ri] = rj
        groups = collections.defaultdict(list)
        for i in range(len(self.triangles)):
            groups[find(i)].append(self.triangles[i])
        return list(groups.values())

    @staticmethod
    def open_edge_count(tris):
        """Edges used by exactly one triangle; 0 means the shell is closed."""
        edges = collections.Counter()
        for t in tris:
            q = [(round(v[0], 5), round(v[1], 5), round(v[2], 5)) for v in t[:3]]
            for a, b in ((q[0], q[1]), (q[1], q[2]), (q[2], q[0])):
                edges[(a, b) if a <= b else (b, a)] += 1
        return sum(1 for n in edges.values() if n == 1)

    def analyze_largest_component(self):
        components = self.get_components()
        if not components:
            raise ValueError(f"{self.filepath} contains no triangles")
        summaries = []
        for c in components:
            ids = collections.Counter(t[3] for t in c)
            summaries.append({
                "volume": self.get_volume(c),
                "triangles": len(c),
                "material_ids": {str(k): v for k, v in ids.most_common()},
                "_tris": c,
            })
        summaries.sort(key=lambda s: s["volume"], reverse=True)
        main = summaries[0]
        ids = collections.Counter(t[3] for t in main["_tris"])
        mat_id, _ = ids.most_common(1)[0]
        warnings = list(self.warnings)
        if len(ids) > 1:
            warnings.append(f"largest component mixes material IDs {dict(ids)}; using majority ID {mat_id}")
        most_tris = max(summaries, key=lambda s: s["triangles"])
        if most_tris is not main:
            warnings.append("the component with the most triangles is not the largest by volume; volume decides")
        open_edges = self.open_edge_count(main["_tris"])
        if open_edges:
            warnings.append(f"largest component has {open_edges} open edges; its volume may be unreliable")
        for s in summaries:
            del s["_tris"]
        return {
            "main_part_volume": main["volume"],
            "main_part_material_id": mat_id,
            "total_components": len(components),
            "components": summaries,
            "open_edges": open_edges,
            "warnings": warnings,
        }


def parse_density_table(path):
    """Read a markdown table with a Material ID column and a Density column.

    Returns ({material_id: (density, name)}, density_unit_header_text).
    """
    rows, header = {}, None
    id_col = dens_col = name_col = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if header is None:
                low = [c.lower() for c in cells]
                id_col = next((i for i, c in enumerate(low) if "id" in c.split() or c.endswith(" id") or c == "id"), None)
                dens_col = next((i for i, c in enumerate(low) if "density" in c), None)
                name_col = next((i for i, c in enumerate(low) if "name" in c), None)
                if id_col is not None and dens_col is not None:
                    header = cells
                continue
            if set("".join(cells)) <= set(":- "):
                continue
            id_m = re.search(r"-?\d+", cells[id_col].replace("*", "")) if id_col < len(cells) else None
            d_m = re.search(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", cells[dens_col].replace("*", "").replace(",", "")) if dens_col < len(cells) else None
            if id_m and d_m:
                name = cells[name_col].replace("*", "").strip() if name_col is not None and name_col < len(cells) else ""
                rows[int(id_m.group())] = (float(d_m.group()), name)
    if header is None:
        raise ValueError(f"{path}: no markdown table with a Material ID column and a Density column")
    return rows, header[dens_col]
