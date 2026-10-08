"""AIP execution step: analyze an STL scan and isolate the main part.

stdin:  {"currentState": {"stl_path": ...}, "assets": {...}, "expects": [...]}
stdout: one JSON object merged over the state.

Splits the mesh into connected components, ranks them by enclosed volume, and reports the
largest (the main part; the rest is scan debris/noise) with its volume in the STL's own
coordinate units cubed and its material ID from the 2-byte binary STL attribute field.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mesh_tool import MeshAnalyzer  # noqa: E402

MAX_COMPONENTS_LISTED = 8


def main():
    payload = json.load(sys.stdin)
    state = payload.get("currentState", payload)
    path = state.get("stl_path")
    if not path:
        print(json.dumps({"error": "stl_path missing from state"}))
        sys.exit(1)
    path = os.path.expanduser(path)
    try:
        an = MeshAnalyzer(path)
    except Exception as e:  # unreadable / missing file
        print(json.dumps({"error": f"cannot read STL {path}: {e}"}))
        sys.exit(1)

    comps = an.component_report()
    issues = list(an.warnings)
    if not comps:
        issues.append("Mesh contains no triangles.")
        main_part = {"volume": 0.0, "material_id": 0, "open_edges": 0, "attribute_histogram": {}}
    else:
        main_part = comps[0]
        nonzero = [k for k in main_part["attribute_histogram"] if k != "0"]
        if not nonzero:
            issues.append("Main part carries no non-zero attribute: material ID unknown (0).")
        elif len(nonzero) > 1:
            issues.append(f"Main part mixes material IDs {main_part['attribute_histogram']}; "
                          f"took the most common non-zero one ({main_part['material_id']}).")
        if main_part["open_edges"]:
            issues.append(f"Main part is not a closed shell ({main_part['open_edges']} open/non-manifold edges); "
                          "its volume may be inaccurate.")
        if len(comps) > 1 and comps[1]["volume"] > 0.5 * main_part["volume"]:
            issues.append(f"Second-largest component is {comps[1]['volume'] / main_part['volume']:.0%} of the main part's "
                          "volume; confirm the main part is a single body and not split across components.")

    out = {
        "mesh_format": an.format,
        "stl_header": an.header,
        "triangle_count": len(an.triangles),
        "total_components": len(comps),
        "main_part_volume": main_part["volume"],
        "main_part_material_id": main_part["material_id"],
        "main_part_attribute_histogram": main_part["attribute_histogram"],
        "main_part_open_edges": main_part["open_edges"],
        "components": comps[:MAX_COMPONENTS_LISTED],
        "mesh_issues": issues,
    }
    print(json.dumps(out))


if __name__ == "__main__":
    main()
