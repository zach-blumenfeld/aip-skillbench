"""Helpers for MATPOWER-format power system network data (PGLib-OPF style JSON).

Use as a library (`from power_flow_data import load_network, ...`) or run with
a filepath argument to print a quick summary:

    python scripts/power_flow_data.py path/to/network.json
"""
from __future__ import annotations

import json
import sys
from typing import Any

import numpy as np


def load_network(filepath: str) -> dict[str, Any]:
    """Load a MATPOWER-format JSON into numpy arrays plus reserve fields.

    The JSON parser is fast even on multi-MB files — never sed/head/tail a
    network JSON.
    """
    with open(filepath) as f:
        data = json.load(f)

    network = {
        "baseMVA": data["baseMVA"],
        "bus": np.array(data["bus"]),
        "gen": np.array(data["gen"]),
        "branch": np.array(data["branch"]),
        "gencost": np.array(data["gencost"]),
    }
    if "reserve_capacity" in data:
        network["reserve_capacity"] = np.array(data["reserve_capacity"])  # MW per generator
    if "reserve_requirement" in data:
        network["reserve_requirement"] = data["reserve_requirement"]      # MW total
    return network


def summarize_network(network: dict[str, Any]) -> dict[str, Any]:
    """Bus/gen/branch counts plus total load. Print this immediately after load."""
    summary = {
        "baseMVA": float(network["baseMVA"]),
        "n_bus": int(len(network["bus"])),
        "n_gen": int(len(network["gen"])),
        "n_branch": int(len(network["branch"])),
        "total_load_mw": float(total_load(network["bus"])),
    }
    if "reserve_requirement" in network:
        summary["reserve_requirement_mw"] = float(network["reserve_requirement"])
    return summary


def build_bus_mapping(buses: np.ndarray) -> dict[int, int]:
    """bus_number -> 0-indexed position. Bus numbers are NOT contiguous in real grids."""
    return {int(buses[i, 0]): i for i in range(len(buses))}


def find_slack_bus(buses: np.ndarray) -> int | None:
    """Return the 0-indexed slack bus (type 3), or None if no slack is declared."""
    for i, bus in enumerate(buses):
        if int(bus[1]) == 3:
            return i
    return None


def get_generators_at_bus(
    gens: np.ndarray, bus_idx: int, bus_num_to_idx: dict[int, int]
) -> list[int]:
    """Generator indices connected to a given 0-indexed bus."""
    out: list[int] = []
    for i, gen in enumerate(gens):
        if bus_num_to_idx[int(gen[0])] == bus_idx:
            out.append(i)
    return out


def get_branch_info(branch: np.ndarray, bus_num_to_idx: dict[int, int]) -> dict[str, Any]:
    """Extract one branch's parameters with bus numbers mapped to 0-indexed positions."""
    return {
        "from_bus": bus_num_to_idx[int(branch[0])],
        "to_bus": bus_num_to_idx[int(branch[1])],
        "resistance": float(branch[2]),     # R in pu
        "reactance": float(branch[3]),      # X in pu
        "susceptance": float(branch[4]),    # B in pu (line charging)
        "rating": float(branch[5]),         # MVA limit (rateA)
        "in_service": int(branch[10]) == 1,
    }


def total_load(buses: np.ndarray) -> float:
    """Total system load in MW (sum of bus Pd, column 2)."""
    return float(sum(bus[2] for bus in buses))


def mw_to_pu(value_mw: float, baseMVA: float) -> float:
    """MW -> per-unit on the system MVA base."""
    return value_mw / baseMVA


def pu_to_mw(value_pu: float, baseMVA: float) -> float:
    """Per-unit -> MW on the system MVA base."""
    return value_pu * baseMVA


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python scripts/power_flow_data.py path/to/network.json", file=sys.stderr)
        sys.exit(2)
    net = load_network(sys.argv[1])
    s = summarize_network(net)
    print(f"baseMVA: {s['baseMVA']}")
    print(f"Buses: {s['n_bus']}")
    print(f"Generators: {s['n_gen']}")
    print(f"Branches: {s['n_branch']}")
    print(f"Total load: {s['total_load_mw']:.1f} MW")
    if "reserve_requirement_mw" in s:
        print(f"Reserve requirement: {s['reserve_requirement_mw']:.1f} MW")
