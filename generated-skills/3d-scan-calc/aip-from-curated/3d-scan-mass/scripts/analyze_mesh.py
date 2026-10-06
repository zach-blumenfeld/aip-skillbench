#!/usr/bin/env python3
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mesh_tool import MeshAnalyzer


def main():
    payload = json.load(sys.stdin)
    state = payload["currentState"]
    stl_path = state["stl_path"]

    analyzer = MeshAnalyzer(stl_path)
    report = analyzer.analyze_largest_component()

    out = {
        "volume_raw": float(report["main_part_volume"]),
        "material_id": int(report["main_part_material_id"]),
        "total_components": int(report["total_components"]),
    }
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
