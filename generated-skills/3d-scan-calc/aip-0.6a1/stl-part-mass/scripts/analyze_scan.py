"""Step analyze-scan: largest connected component's volume, Material ID, and density.

stdin:  {"state": {"stl_path", "density_table_path"}, "assets", "expects"}
stdout: {"main_part_volume", "material_id", "density", "density_unit", "material_name", "mesh_report"}
"""

import json
import sys

from mesh_tool import MeshAnalyzer, parse_density_table


def main():
    state = json.load(sys.stdin)["state"]
    analyzer = MeshAnalyzer(state["stl_path"])
    report = analyzer.analyze_largest_component()
    mat_id = int(report["main_part_material_id"])

    table, density_header = parse_density_table(state["density_table_path"])
    if mat_id not in table:
        sys.exit(
            f"Material ID {mat_id} of the largest component is not in {state['density_table_path']} "
            f"(table IDs: {sorted(table)}). Do not guess a density."
            + (" The file parsed as ASCII STL, which has no attribute bytes, so every ID reads 0." if analyzer.format == "ascii" else "")
        )
    density, name = table[mat_id]

    comps = report["components"]
    mesh_report = {
        "format": analyzer.format,
        "triangles": len(analyzer.triangles),
        "total_components": report["total_components"],
        "main_part_triangles": comps[0]["triangles"],
        "main_part_open_edges": report["open_edges"],
        "largest_components": comps[:5],
        "debris_volume_total": sum(c["volume"] for c in comps[1:]),
        "table_material_ids": sorted(table),
        "warnings": report["warnings"],
    }
    json.dump({
        "main_part_volume": report["main_part_volume"],
        "material_id": mat_id,
        "density": density,
        "density_unit": density_header,
        "material_name": name,
        "mesh_report": mesh_report,
    }, sys.stdout)


if __name__ == "__main__":
    main()
