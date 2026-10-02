#!/usr/bin/env python3
"""Compute impact_analysis from base_case + counterfactual and write report.json.

Reads {currentState, ...} from stdin. Requires state keys:
  base_case, counterfactual (from prior steps),
  scenario_from_bus, scenario_to_bus (start inputs),
  output_path (string, where to write report.json).

Writes {"impact_analysis": {...}, "report": {...}, "report_path": str} to stdout.
"""
import json
import sys


def _binding_pair_set(binding_lines):
    """Set of unordered (from,to) tuples for line-identity comparisons."""
    s = set()
    for entry in binding_lines:
        a, b = int(entry["from"]), int(entry["to"])
        s.add((a, b))
        s.add((b, a))
    return s


def main() -> None:
    payload = json.load(sys.stdin)
    state = payload.get("currentState", {})

    base = state["base_case"]
    cf = state["counterfactual"]
    target_from = int(state["scenario_from_bus"])
    target_to = int(state["scenario_to_bus"])
    output_path = state["output_path"]

    base_cost = base["total_cost_dollars_per_hour"]
    cf_cost = cf["total_cost_dollars_per_hour"]
    cost_reduction = round(base_cost - cf_cost, 2)

    base_map = {e["bus"]: e["lmp_dollars_per_MWh"] for e in base["lmp_by_bus"]}
    cf_map = {e["bus"]: e["lmp_dollars_per_MWh"] for e in cf["lmp_by_bus"]}

    deltas = []
    for bus_num, base_lmp in base_map.items():
        cf_lmp = cf_map.get(bus_num)
        if cf_lmp is None:
            continue
        deltas.append(
            {
                "bus": int(bus_num),
                "base_lmp": base_lmp,
                "cf_lmp": cf_lmp,
                "delta": round(cf_lmp - base_lmp, 2),
            }
        )
    # Most negative delta = largest drop
    deltas.sort(key=lambda x: x["delta"])
    top3 = deltas[:3]

    base_binding = _binding_pair_set(base["binding_lines"])
    cf_binding = _binding_pair_set(cf["binding_lines"])
    was_binding = (target_from, target_to) in base_binding
    still_binding = (target_from, target_to) in cf_binding
    congestion_relieved = bool(was_binding and not still_binding)

    impact = {
        "cost_reduction_dollars_per_hour": cost_reduction,
        "buses_with_largest_lmp_drop": top3,
        "congestion_relieved": congestion_relieved,
    }

    report = {
        "base_case": base,
        "counterfactual": cf,
        "impact_analysis": impact,
    }

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    json.dump(
        {"impact_analysis": impact, "report": report, "report_path": output_path},
        sys.stdout,
    )


if __name__ == "__main__":
    main()
