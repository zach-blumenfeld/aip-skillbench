#!/usr/bin/env python3
"""Solve the base-case DC-OPF with reserve co-optimization.

Reads {currentState, assets, expects} from stdin, writes {"base_case": {...}} to stdout.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _dcopf import bootstrap, load_network, solve_dcopf_with_reserves


def main() -> None:
    bootstrap()
    payload = json.load(sys.stdin)
    state = payload.get("currentState", {})
    network = load_network(state["network_path"])
    result = solve_dcopf_with_reserves(network, network["branch"])
    json.dump({"base_case": result}, sys.stdout)


if __name__ == "__main__":
    main()
