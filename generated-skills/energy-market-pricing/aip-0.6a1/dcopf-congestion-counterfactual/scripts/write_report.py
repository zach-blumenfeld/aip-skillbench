#!/usr/bin/env python3
"""Check the three report sections against the required report.json structure and
write the file.

stdin : {"state": {base_case, counterfactual, impact_analysis, report_path}, ...}
stdout: {"report_file": <absolute path written>, "report_summary": {...}}
Exits non-zero (writing nothing) if any required field is missing or mistyped.
"""

import json
import os
import sys

CASE_KEYS = {
    "total_cost_dollars_per_hour": (int, float),
    "lmp_by_bus": list,
    "reserve_mcp_dollars_per_MWh": (int, float),
    "binding_lines": list,
}
LINE_KEYS = ("from", "to", "flow_MW", "limit_MW")
DROP_KEYS = ("bus", "base_lmp", "cf_lmp", "delta")


def check(state):
    errs = []
    for name in ("base_case", "counterfactual"):
        case = state[name]
        for k, typ in CASE_KEYS.items():
            if not isinstance(case.get(k), typ) or isinstance(case.get(k), bool):
                errs.append(f"{name}.{k} missing or not {typ}")
        for row in case.get("lmp_by_bus", []):
            if set(row) != {"bus", "lmp_dollars_per_MWh"}:
                errs.append(f"{name}.lmp_by_bus row has keys {sorted(row)}")
                break
        for row in case.get("binding_lines", []):
            if set(row) != set(LINE_KEYS):
                errs.append(f"{name}.binding_lines row has keys {sorted(row)}")
                break
    nb, nc = len(state["base_case"].get("lmp_by_bus", [])), len(state["counterfactual"].get("lmp_by_bus", []))
    if nb != nc or nb == 0:
        errs.append(f"lmp_by_bus lengths differ or are empty: base {nb}, counterfactual {nc}")
    imp = state["impact_analysis"]
    if not isinstance(imp.get("cost_reduction_dollars_per_hour"), (int, float)):
        errs.append("impact_analysis.cost_reduction_dollars_per_hour missing")
    drops = imp.get("buses_with_largest_lmp_drop")
    if not isinstance(drops, list) or len(drops) != min(3, nb):
        errs.append("impact_analysis.buses_with_largest_lmp_drop must list 3 buses")
    else:
        for row in drops:
            if set(row) != set(DROP_KEYS):
                errs.append(f"buses_with_largest_lmp_drop row has keys {sorted(row)}")
                break
    if not isinstance(imp.get("congestion_relieved"), bool):
        errs.append("impact_analysis.congestion_relieved must be a boolean")
    return errs


def main():
    state = json.load(sys.stdin)["state"]
    errs = check(state)
    if errs:
        sys.exit("report.json not written: " + "; ".join(errs))
    report = {
        "base_case": state["base_case"],
        "counterfactual": state["counterfactual"],
        "impact_analysis": state["impact_analysis"],
    }
    path = os.path.abspath(os.path.expanduser(state["report_path"]))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    imp = report["impact_analysis"]
    print(json.dumps({
        "report_file": path,
        "report_summary": {
            "n_buses": len(report["base_case"]["lmp_by_bus"]),
            "base_cost": report["base_case"]["total_cost_dollars_per_hour"],
            "cf_cost": report["counterfactual"]["total_cost_dollars_per_hour"],
            "cost_reduction": imp["cost_reduction_dollars_per_hour"],
            "n_binding_base": len(report["base_case"]["binding_lines"]),
            "n_binding_cf": len(report["counterfactual"]["binding_lines"]),
            "top_drop_buses": [r["bus"] for r in imp["buses_with_largest_lmp_drop"]],
            "congestion_relieved": imp["congestion_relieved"],
        },
    }))


if __name__ == "__main__":
    main()
