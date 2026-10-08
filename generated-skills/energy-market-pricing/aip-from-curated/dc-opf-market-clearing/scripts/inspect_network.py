#!/usr/bin/env python3
"""Inspect a MATPOWER-style network.json and check the requested scenario against it.

Standard library only (runs before any dependency bootstrap). Reads one JSON object on
stdin: {"currentState": {...}, "assets": {...}, "expects": [...]} and writes one JSON
object to stdout.

State keys used:
  network_path    path to network.json (MATPOWER arrays: bus, gen, branch, gencost,
                  optional reserve_capacity / reserve_requirement)
  counterfactual  {"enabled": bool, "modifications": [ ... ]} (see solve_market.py)
"""
import json
import os
import sys
from collections import Counter

# MATPOWER column indices (0-based)
BUS_I, BUS_TYPE, PD = 0, 1, 2
GEN_BUS, GEN_STATUS, PMAX, PMIN = 0, 7, 8, 9
F_BUS, T_BUS, BR_X, RATE_A, TAP, SHIFT, BR_STATUS = 0, 1, 3, 5, 8, 9, 10
MODEL, NCOST, COST = 0, 3, 4

MOD_TYPES = {"line_limit", "bus_load", "reserve_requirement"}


def fail(msg):
    print(json.dumps({"inputs_ok": False, "issues": [msg], "network_summary": {}}))
    sys.exit(0)


def main():
    payload = json.load(sys.stdin)
    state = payload.get("currentState", payload)
    path = os.path.expanduser(str(state.get("network_path", "")))
    if not path or not os.path.isfile(path):
        fail(f"network_path not found: {path!r}")
    try:
        with open(path) as f:
            data = json.load(f)  # never read large network files line by line
    except Exception as e:  # noqa: BLE001
        fail(f"could not parse {path} as JSON: {e}")

    issues, warnings = [], []
    for key in ("baseMVA", "bus", "gen", "branch", "gencost"):
        if key not in data:
            issues.append(f"missing top-level key '{key}'")
    if issues:
        print(json.dumps({"inputs_ok": False, "issues": issues, "network_summary": {}}))
        return

    bus, gen, br, gc = data["bus"], data["gen"], data["branch"], data["gencost"]
    bus_nums = [int(b[BUS_I]) for b in bus]
    bus_set = set(bus_nums)
    contiguous = bus_nums == list(range(1, len(bus) + 1))
    slack = [int(b[BUS_I]) for b in bus if int(b[BUS_TYPE]) == 3]
    if len(slack) != 1:
        warnings.append(f"{len(slack)} slack (type 3) buses found; solver uses the first, or bus index 0 if none")
    bad_gen_bus = [int(g[GEN_BUS]) for g in gen if int(g[GEN_BUS]) not in bus_set]
    bad_br_bus = [(int(r[F_BUS]), int(r[T_BUS])) for r in br
                  if int(r[F_BUS]) not in bus_set or int(r[T_BUS]) not in bus_set]
    if bad_gen_bus:
        issues.append(f"generators reference unknown buses: {bad_gen_bus[:10]}")
    if bad_br_bus:
        issues.append(f"branches reference unknown buses: {bad_br_bus[:10]}")
    if len(gc) != len(gen):
        issues.append(f"gencost rows ({len(gc)}) != gen rows ({len(gen)})")

    models = Counter(int(c[MODEL]) for c in gc)
    ncosts = Counter(int(c[NCOST]) for c in gc)
    quad = sum(1 for c in gc if int(c[MODEL]) == 2 and int(c[NCOST]) >= 3 and float(c[COST]) != 0)
    if any(int(c[MODEL]) == 2 and int(c[NCOST]) > 3 for c in gc):
        issues.append("polynomial cost with NCOST > 3 (cubic or higher) is not supported by the convex solver")

    has_reserves = "reserve_capacity" in data and "reserve_requirement" in data
    if has_reserves and len(data["reserve_capacity"]) != len(gen):
        issues.append("reserve_capacity length != number of generators")

    total_load = sum(float(b[PD]) for b in bus)
    in_service = [g for g in gen if float(g[GEN_STATUS]) > 0]
    total_pmax = sum(float(g[PMAX]) for g in in_service)
    total_pmin = sum(float(g[PMIN]) for g in in_service)
    if total_pmax < total_load:
        issues.append(f"in-service Pmax {total_pmax:.1f} MW < total load {total_load:.1f} MW (infeasible)")
    if total_pmin > total_load:
        issues.append(f"in-service Pmin {total_pmin:.1f} MW > total load {total_load:.1f} MW (infeasible)")
    if has_reserves:
        rsum = sum(float(r) for r, g in zip(data["reserve_capacity"], gen) if float(g[GEN_STATUS]) > 0)
        if rsum < float(data["reserve_requirement"]):
            issues.append(f"sum of reserve_capacity {rsum:.1f} MW < reserve_requirement")

    pair_count = Counter((min(int(r[F_BUS]), int(r[T_BUS])), max(int(r[F_BUS]), int(r[T_BUS]))) for r in br)
    summary = {
        "name": data.get("name"),
        "baseMVA": data["baseMVA"],
        "n_bus": len(bus), "n_gen": len(gen), "n_branch": len(br),
        "bus_numbers_contiguous": contiguous,
        "slack_buses": slack,
        "bus_type_counts": {str(k): v for k, v in Counter(int(b[BUS_TYPE]) for b in bus).items()},
        "total_load_MW": round(total_load, 2),
        "total_pmax_MW_in_service": round(total_pmax, 2),
        "total_pmin_MW_in_service": round(total_pmin, 2),
        "gens_out_of_service": len(gen) - len(in_service),
        "branches_out_of_service": sum(1 for r in br if float(r[BR_STATUS]) == 0),
        "branches_rate_a_zero_unlimited": sum(1 for r in br if float(r[RATE_A]) <= 0),
        "branches_x_zero": sum(1 for r in br if float(r[BR_X]) == 0),
        "branches_with_tap": sum(1 for r in br if float(r[TAP]) not in (0.0, 1.0)),
        "branches_with_shift": sum(1 for r in br if float(r[SHIFT]) != 0),
        "parallel_branch_extra_circuits": sum(v - 1 for v in pair_count.values() if v > 1),
        "gencost_models": {str(k): v for k, v in models.items()},
        "gencost_ncost": {str(k): v for k, v in ncosts.items()},
        "gens_with_quadratic_cost": quad,
        "has_reserves": has_reserves,
        "reserve_requirement_MW": data.get("reserve_requirement"),
    }

    # Check the counterfactual modifications against the network.
    cf = state.get("counterfactual") or {}
    targets = []
    if cf.get("enabled"):
        mods = cf.get("modifications") or []
        if not mods:
            issues.append("counterfactual.enabled is true but modifications is empty")
        for i, m in enumerate(mods):
            t = m.get("type")
            if t not in MOD_TYPES:
                issues.append(f"modification {i}: unknown type {t!r}; use one of {sorted(MOD_TYPES)}")
                continue
            if t == "line_limit":
                fb, tb = m.get("from_bus"), m.get("to_bus")
                if fb is None or tb is None:
                    issues.append(f"modification {i}: line_limit needs from_bus and to_bus")
                    continue
                if ("factor" in m) == ("limit_MW" in m):
                    issues.append(f"modification {i}: line_limit needs exactly one of factor or limit_MW")
                matches = [k for k, r in enumerate(br)
                           if {int(r[F_BUS]), int(r[T_BUS])} == {int(fb), int(tb)}]
                if not matches:
                    issues.append(f"modification {i}: no branch between buses {fb} and {tb}")
                    continue
                if len(matches) > 1 and m.get("match", "first") == "first":
                    warnings.append(f"modification {i}: {len(matches)} parallel circuits between {fb}-{tb}; "
                                    "only the first (lowest branch index) is modified unless match='all'")
                targets.append({"modification": i, "from_bus": int(fb), "to_bus": int(tb),
                                "branch_indices_0based": matches,
                                "stored_direction": [[int(br[k][F_BUS]), int(br[k][T_BUS])] for k in matches],
                                "rate_a_MW": [float(br[k][RATE_A]) for k in matches],
                                "x_pu": [float(br[k][BR_X]) for k in matches]})
            elif t == "bus_load":
                b = m.get("bus")
                if b is None or int(b) not in bus_set:
                    issues.append(f"modification {i}: bus_load bus {b!r} not in network")
                if sum(k in m for k in ("factor", "delta_MW", "pd_MW")) != 1:
                    issues.append(f"modification {i}: bus_load needs exactly one of factor, delta_MW, pd_MW")
            elif t == "reserve_requirement":
                if not has_reserves:
                    issues.append(f"modification {i}: network has no reserve data")
                if ("factor" in m) == ("value_MW" in m):
                    issues.append(f"modification {i}: reserve_requirement needs exactly one of factor or value_MW")

    print(json.dumps({
        "inputs_ok": not issues,
        "issues": issues,
        "warnings": warnings,
        "network_summary": summary,
        "counterfactual_targets": targets,
    }))


if __name__ == "__main__":
    main()
