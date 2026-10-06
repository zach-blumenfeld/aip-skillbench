#!/usr/bin/env python3
"""Relax the most binding line and re-solve to quantify congestion impact.

Picks the binding line with the highest loading percentage from
`base_results.binding_lines`. If multiple binding lines exist, ties are
broken by largest absolute flow. The chosen line's RATE_A is multiplied
by `counterfactual_scale` (default 1.2 = +20%). The scaled DC-OPF is
re-solved and the diff vs base is computed.

stdin:  {"currentState": {"network_path": str, "base_results": {...}, "counterfactual_scale": float?, ...}, "assets": {}, "expects": {...}}
stdout: adds `counterfactual_results`, `counterfactual_target`, `counterfactual_scale`, and `impact` to the state.
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
base = state["base_results"]
scale = float(state.get("counterfactual_scale") or 1.20)

binding = base.get("binding_lines") or []
if not binding:
    raise RuntimeError(
        "No binding lines in base_results; counterfactual analysis is not meaningful."
    )
binding_sorted = sorted(
    binding, key=lambda r: (r["loading_pct"], abs(r["flow_MW"])), reverse=True
)
target = binding_sorted[0]
target_from = int(target["from"])
target_to = int(target["to"])
original_limit = float(target["limit_MW"])

net = load_network(network_path)
branches = net["branch"]
modified = False
for k in range(len(branches)):
    br_from, br_to = int(branches[k, 0]), int(branches[k, 1])
    if (br_from == target_from and br_to == target_to) or (
        br_from == target_to and br_to == target_from
    ):
        branches[k, 5] = branches[k, 5] * scale
        modified = True
        break
if not modified:
    raise RuntimeError(f"Target line {target_from}->{target_to} not found in branches")

cf = solve_dcopf(net)

cost_reduction = round(base["cost_dollars_per_hour"] - cf["cost_dollars_per_hour"], 2)

base_lmp_map = {r["bus"]: r["lmp_dollars_per_MWh"] for r in base["lmps"]}
cf_lmp_map = {r["bus"]: r["lmp_dollars_per_MWh"] for r in cf["lmps"]}
lmp_deltas = []
for bus, base_lmp in base_lmp_map.items():
    cf_lmp = cf_lmp_map.get(bus, 0.0)
    lmp_deltas.append({
        "bus": bus,
        "base_lmp": base_lmp,
        "counterfactual_lmp": cf_lmp,
        "delta_dollars_per_MWh": round(cf_lmp - base_lmp, 2),
    })

cf_binding_pairs = {(r["from"], r["to"]) for r in cf.get("binding_lines", [])}
congestion_relieved = (
    (target_from, target_to) not in cf_binding_pairs
    and (target_to, target_from) not in cf_binding_pairs
)

impact = {
    "cost_reduction_dollars_per_hour": cost_reduction,
    "congestion_relieved": bool(congestion_relieved),
    "n_binding_before": len(base.get("binding_lines", [])),
    "n_binding_after": len(cf.get("binding_lines", [])),
    "lmp_deltas": lmp_deltas,
}
target_record = {
    "from": target_from,
    "to": target_to,
    "original_limit_MW": round(original_limit, 2),
    "relaxed_limit_MW": round(original_limit * scale, 2),
    "loading_pct_base": target["loading_pct"],
}

json.dump({
    "counterfactual_scale": scale,
    "counterfactual_target": target_record,
    "counterfactual_results": cf,
    "impact": impact,
}, sys.stdout)
