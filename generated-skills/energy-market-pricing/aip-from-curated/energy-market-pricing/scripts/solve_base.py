#!/usr/bin/env python3
"""Solve the base-case DC-OPF with reserves and extract LMPs.

stdin:  {"currentState": {"network_path": str, ...}, "assets": {}, "expects": {...}}
stdout: adds `base_results` (and echoes `network_path`) to the state.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _dcopf import load_network, solve_dcopf  # noqa: E402

payload = json.load(sys.stdin)
state = payload["currentState"]
network_path = state["network_path"]

net = load_network(network_path)
results = solve_dcopf(net)

json.dump({"network_path": network_path, "base_results": results}, sys.stdout)
