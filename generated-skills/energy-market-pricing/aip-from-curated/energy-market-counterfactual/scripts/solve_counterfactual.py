#!/usr/bin/env python3
"""Apply the counterfactual line-limit modification and re-solve DC-OPF.

Reads {currentState, assets, expects} from stdin.
Requires state keys: network_path (string), scenario_from_bus (int),
scenario_to_bus (int), scenario_delta_pct (float).
Writes {"counterfactual": {...}, "modified_line": {...}} to stdout.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _dcopf import apply_line_limit_change, bootstrap, load_network, solve_dcopf_with_reserves


def main() -> None:
    bootstrap()
    payload = json.load(sys.stdin)
    state = payload.get("currentState", {})

    network = load_network(state["network_path"])
    cf_branches, _idx, old_limit, new_limit = apply_line_limit_change(
        network["branch"],
        int(state["scenario_from_bus"]),
        int(state["scenario_to_bus"]),
        float(state["scenario_delta_pct"]),
    )
    result = solve_dcopf_with_reserves(network, cf_branches)
    json.dump(
        {
            "counterfactual": result,
            "modified_line": {
                "from": int(state["scenario_from_bus"]),
                "to": int(state["scenario_to_bus"]),
                "old_limit_MW": round(old_limit, 2),
                "new_limit_MW": round(new_limit, 2),
            },
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
