#!/usr/bin/env python3
"""AIP execution step: analyze an STL, isolate the largest connected component,
return its volume + material_id + component count. Stdlib only."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mesh_tool import MeshAnalyzer


def main() -> None:
    payload = json.load(sys.stdin)
    state = payload.get("currentState", {})
    stl_path = state["stl_path"]

    analyzer = MeshAnalyzer(stl_path)
    report = analyzer.analyze_largest_component()

    out = {
        "main_part_volume": float(report["main_part_volume"]),
        "main_part_material_id": int(report["main_part_material_id"]),
        "total_components": int(report["total_components"]),
    }
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
