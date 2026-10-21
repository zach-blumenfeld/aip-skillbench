#!/usr/bin/env python3
"""Mass of the main part in a (noisy) scanned STL.

Requires: Python >= 3.8, standard library only (struct, collections, json, re, argparse).

Pipeline: parse STL (binary with per-triangle 2-byte attribute = Material ID; ASCII
fallback has no IDs) -> connected components by shared vertices (coords rounded to 5
decimals) -> pick the component with the largest enclosed volume (divergence theorem)
-> Material ID of that component -> density lookup in a markdown table ->
mass = volume * volume_scale * density -> JSON report.

Usage:
  python3 scripts/mesh_mass.py analyze STL
  python3 scripts/mesh_mass.py mass STL DENSITY_TABLE.md --out REPORT.json
        [--volume-scale F] [--subtract-voids] [--decimals N] [--component I]

Also importable: from mesh_mass import MeshAnalyzer (same API as the original
mesh-analysis tool: analyze_largest_component(), get_components(), get_volume()).
"""
import argparse
import collections
import json
import os
import re
import struct
import sys


class MeshAnalyzer:
    def __init__(self, filepath):
        self.filepath = filepath
        self.triangles = []  # (v1, v2, v3, attr)
        self.format = None
        self.warnings = []
        self._parse()

    # ---------- parsing ----------
    def _parse(self):
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"{self.filepath} not found.")
        size = os.path.getsize(self.filepath)
        with open(self.filepath, "rb") as f:
            head = f.read(84)
        count = struct.unpack("<I", head[80:84])[0] if len(head) >= 84 else None
        expected = 84 + 50 * count if count is not None else None
        if expected is not None and count > 0 and size == expected:
            self._parse_binary(count)
        elif expected is not None and count > 0 and size > expected and not head.lstrip().startswith(b"solid"):
            self.warnings.append(f"binary STL has {size - expected} trailing bytes; ignored")
            self._parse_binary(count)
        else:
            self._parse_ascii()
            if not self.triangles:
                raise ValueError(
                    f"Could not parse {self.filepath}: size {size} does not match binary layout "
                    f"(84 + 50*{count} = {expected}) and no ASCII facets found."
                )
            self.warnings.append("ASCII STL: no attribute bytes, Material ID defaults to 0")

    def _parse_binary(self, count):
        self.format = "binary"
        with open(self.filepath, "rb") as f:
            f.seek(84)
            data = f.read(50 * count)
        rec = struct.Struct("<12fH")
        for off in range(0, 50 * count, 50):
            v = rec.unpack_from(data, off)
            self.triangles.append(((v[3], v[4], v[5]), (v[6], v[7], v[8]), (v[9], v[10], v[11]), v[12]))

    def _parse_ascii(self):
        self.format = "ascii"
        cur = []
        with open(self.filepath, errors="replace") as f:
            for line in f:
                parts = line.strip().split()
                if not parts:
                    continue
                if parts[0] == "vertex":
                    cur.append((float(parts[1]), float(parts[2]), float(parts[3])))
                elif parts[0] == "endfacet":
                    if len(cur) == 3:
                        self.triangles.append((cur[0], cur[1], cur[2], 0))
                    cur = []

    # ---------- geometry ----------
    @staticmethod
    def signed_volume(tris):
        total = 0.0
        for v1, v2, v3, _ in tris:
            cx = v2[1] * v3[2] - v2[2] * v3[1]
            cy = v2[2] * v3[0] - v2[0] * v3[2]
            cz = v2[0] * v3[1] - v2[1] * v3[0]
            total += v1[0] * cx + v1[1] * cy + v1[2] * cz
        return total / 6.0

    def get_volume(self, triangles=None):
        tris = triangles if triangles is not None else self.triangles
        return abs(self.signed_volume(tris))

    @staticmethod
    def _q(v):
        return (round(v[0], 5), round(v[1], 5), round(v[2], 5))

    def get_component_indices(self):
        vmap = collections.defaultdict(list)
        for i, t in enumerate(self.triangles):
            for v in t[:3]:
                vmap[self._q(v)].append(i)
        seen = bytearray(len(self.triangles))
        comps = []
        for i in range(len(self.triangles)):
            if seen[i]:
                continue
            seen[i] = 1
            stack, comp = [i], []
            while stack:
                c = stack.pop()
                comp.append(c)
                for v in self.triangles[c][:3]:
                    for n in vmap[self._q(v)]:
                        if not seen[n]:
                            seen[n] = 1
                            stack.append(n)
            comps.append(comp)
        return comps

    def get_components(self):
        return [[self.triangles[i] for i in c] for c in self.get_component_indices()]

    def edge_check(self, tris):
        """Closed + consistently oriented iff every directed edge has exactly one reverse partner."""
        directed = collections.Counter()
        for t in tris:
            a, b, c = (self._q(t[0]), self._q(t[1]), self._q(t[2]))
            for e in ((a, b), (b, c), (c, a)):
                directed[e] += 1
        open_edges = sum(1 for (a, b), n in directed.items() if directed.get((b, a), 0) == 0)
        bad = sum(1 for (a, b), n in directed.items() if n != 1 or directed.get((b, a), 0) != 1)
        return {"watertight_oriented": bad == 0, "open_edges": open_edges, "bad_directed_edges": bad}

    def describe(self):
        comps = []
        for idx in self.get_component_indices():
            tris = [self.triangles[i] for i in idx]
            sv = self.signed_volume(tris)
            xs = [v for t in tris for v in t[:3]]
            bmin = [min(p[k] for p in xs) for k in range(3)]
            bmax = [max(p[k] for p in xs) for k in range(3)]
            ids = collections.Counter(t[3] for t in tris)
            comps.append({"tris": tris, "triangles": len(tris), "signed_volume": sv, "volume": abs(sv),
                          "material_ids": dict(ids), "bbox_min": bmin, "bbox_max": bmax})
        comps.sort(key=lambda c: c["volume"], reverse=True)
        return comps

    def analyze_largest_component(self):
        comps = self.describe()
        if not comps:
            return {"main_part_volume": 0.0, "main_part_material_id": 0, "total_components": 0}
        main = comps[0]
        return {"main_part_volume": main["volume"],
                "main_part_material_id": collections.Counter(t[3] for t in main["tris"]).most_common(1)[0][0],
                "total_components": len(comps)}


def _inside(c, m):
    return all(m["bbox_min"][k] <= c["bbox_min"][k] and c["bbox_max"][k] <= m["bbox_max"][k] for k in range(3))


def build_report(stl, pick=0):
    an = MeshAnalyzer(stl)
    comps = an.describe()
    if not comps:
        sys.exit(f"ERROR: {stl} contains no triangles.")
    if not 0 <= pick < len(comps):
        sys.exit(f"ERROR: --component {pick} out of range (0..{len(comps) - 1}).")
    main = comps[pick]
    warnings = list(an.warnings)
    ids = main["material_ids"]
    mat_id = max(ids.items(), key=lambda kv: kv[1])[0]
    if len(ids) > 1:
        warnings.append(f"main component has mixed Material IDs {ids}; using majority ID {mat_id}")
    edge = an.edge_check(main["tris"])
    if not edge["watertight_oriented"]:
        warnings.append(f"main component is not closed/consistently oriented ({edge}); volume may be wrong")
    by_count = max(comps, key=lambda c: c["triangles"])
    if pick == 0 and by_count is not main and by_count["triangles"] > main["triangles"]:
        warnings.append(f"largest-by-volume component ({main['triangles']} tris) differs from "
                        f"largest-by-triangle-count component ({by_count['triangles']} tris, "
                        f"volume {by_count['volume']:.6g}); selection uses volume")
    if pick == 0 and len(comps) > 1 and comps[1]["volume"] > 0.5 * main["volume"]:
        warnings.append(f"runner-up component volume {comps[1]['volume']:.6g} is >50% of the main part's; "
                        "selection is not clear-cut")
    voids = [c for c in comps if c is not main
             if _inside(c, main) and c["signed_volume"] * main["signed_volume"] < 0 and mat_id in c["material_ids"]]
    if voids:
        warnings.append(f"{len(voids)} inward-facing shell(s) with the main Material ID lie inside the main part "
                        f"(total {sum(v['volume'] for v in voids):.6g}); possible internal voids")
    return an, comps, main, mat_id, edge, voids, warnings


def parse_density_table(path):
    """Return {material_id: density} from a markdown table with 'ID' and 'Density' header columns."""
    table, id_col, den_col, header, found = {}, None, None, None, None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s.startswith("|"):
                id_col = den_col = header = None
                continue
            cells = [re.sub(r"[*_`]", "", c).strip() for c in s.strip("|").split("|")]
            if id_col is None:
                low = [c.lower() for c in cells]
                ic = next((i for i, c in enumerate(low) if "id" in c.split() or c.endswith(" id") or c == "id"), None)
                dc = next((i for i, c in enumerate(low) if "density" in c), None)
                if ic is not None and dc is not None:
                    id_col, den_col, header = ic, dc, cells[dc]
                continue
            if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
                continue
            try:
                mid = int(re.search(r"-?\d+", cells[id_col]).group())
                den = float(re.search(r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?", cells[den_col]).group())
            except (AttributeError, IndexError, ValueError):
                continue
            table[mid] = den
            found = header
    if not table:
        sys.exit(f"ERROR: no table with 'Material ID' and 'Density' columns found in {path}")
    return table, found


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="list components; no output file")
    a.add_argument("stl")
    m = sub.add_parser("mass", help="compute main-part mass and write JSON")
    m.add_argument("stl")
    m.add_argument("density_table")
    m.add_argument("--out", required=True)
    m.add_argument("--volume-scale", type=float, default=1.0,
                   help="multiply STL-unit volume by this to get the density table's volume unit (default 1)")
    m.add_argument("--subtract-voids", action="store_true",
                   help="subtract flagged internal void shells from the main volume")
    m.add_argument("--decimals", type=int, default=4)
    m.add_argument("--component", type=int, default=0,
                   help="index in the analyze listing to treat as the main part (default 0 = largest volume)")
    args = ap.parse_args()

    an, comps, main_c, mat_id, edge, voids, warnings = build_report(args.stl, getattr(args, "component", 0))
    print(f"format={an.format} triangles={len(an.triangles)} components={len(comps)}")
    for i, c in enumerate(comps[:10]):
        print(f"  #{i} tris={c['triangles']} volume={c['volume']:.6f} signed={c['signed_volume']:.6f} "
              f"ids={c['material_ids']} bbox={[round(x, 3) for x in c['bbox_min']]}..{[round(x, 3) for x in c['bbox_max']]}")
    if len(comps) > 10:
        print(f"  ... {len(comps) - 10} smaller components")
    print(f"main part (#{getattr(args, 'component', 0)}): volume={main_c['volume']:.6f} material_id={mat_id} edge_check={edge}")
    for w in warnings:
        print(f"WARNING: {w}")
    if args.cmd == "analyze":
        return

    if an.format != "binary":
        sys.exit("ERROR: ASCII STL carries no Material ID attribute; the material must come from elsewhere.")
    table, header = parse_density_table(args.density_table)
    if mat_id not in table:
        sys.exit(f"ERROR: Material ID {mat_id} not in density table (IDs: {sorted(table)}).")
    vol = main_c["volume"]
    if args.subtract_voids and voids:
        vol -= sum(v["volume"] for v in voids)
        print(f"subtracted {len(voids)} void(s): net volume={vol:.6f}")
    density = table[mat_id]
    mass = vol * args.volume_scale * density
    report = {"main_part_mass": round(mass, args.decimals), "material_id": int(mat_id)}
    with open(args.out, "w") as f:
        json.dump(report, f, indent=1)
        f.write("\n")
    print(f"density[{mat_id}]={density} ({header}) volume_scale={args.volume_scale} mass={mass:.6f}")
    print(f"wrote {args.out}: {json.dumps(report)}")


if __name__ == "__main__":
    main()
