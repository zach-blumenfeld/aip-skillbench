#!/usr/bin/env python3
"""Parse a binary STL, filter to the largest connected component, extract volume and material ID.

stdin:  {"currentState": {"stl_path": str, ...}, "assets": {...}, "expects": {...}}
stdout: {"main_part_volume": float, "material_id": int, "total_components": int}
"""
import contextlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mesh_tool import MeshAnalyzer

payload = json.load(sys.stdin)
state = payload["currentState"]

with contextlib.redirect_stdout(sys.stderr):
    analyzer = MeshAnalyzer(state["stl_path"])
    report = analyzer.analyze_largest_component()

json.dump(
    {
        "main_part_volume": float(report["main_part_volume"]),
        "material_id": int(report["main_part_material_id"]),
        "total_components": int(report["total_components"]),
    },
    sys.stdout,
)
