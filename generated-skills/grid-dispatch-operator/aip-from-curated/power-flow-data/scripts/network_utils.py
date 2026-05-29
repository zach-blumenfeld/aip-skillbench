"""MATPOWER-format network parsing utilities.

Loads PGLib-OPF style network JSON and exposes helpers for bus-number
mapping, slack-bus location, generator-to-bus lookup, branch
interpretation, and aggregate load.

Designed to be imported by an analysis script:

    from network_utils import load_network, find_slack_bus, total_load
    net = load_network('network.json')
    print(f"buses={len(net['bus'])} slack={find_slack_bus(net['bus'])}")
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np


# MATPOWER bus-type codes
BUS_TYPE_PQ = 1     # load bus: P, Q specified; V, theta solved
BUS_TYPE_PV = 2     # generator bus: P, V specified; Q, theta solved
BUS_TYPE_SLACK = 3  # reference bus: V, theta=0 specified; P, Q solved


def load_network(filepath: str) -> dict[str, Any]:
    """Load MATPOWER-format network JSON into numpy arrays.

    Returns a dict with baseMVA, bus, gen, branch, gencost, and (when
    present) reserve_capacity and reserve_requirement.
    """
    with open(filepath) as f:
        data = json.load(f)

    net: dict[str, Any] = {
        'baseMVA': data['baseMVA'],
        'bus': np.array(data['bus']),
        'gen': np.array(data['gen']),
        'branch': np.array(data['branch']),
        'gencost': np.array(data['gencost']),
    }
    if 'reserve_capacity' in data:
        net['reserve_capacity'] = np.array(data['reserve_capacity'])
    if 'reserve_requirement' in data:
        net['reserve_requirement'] = data['reserve_requirement']
    return net


def summarize(net: dict[str, Any]) -> dict[str, Any]:
    """Quick scalar summary — bus / gen / branch counts and total load."""
    return {
        'baseMVA': float(net['baseMVA']),
        'n_bus': len(net['bus']),
        'n_gen': len(net['gen']),
        'n_branch': len(net['branch']),
        'total_load_MW': total_load(net['bus']),
        'reserve_requirement_MW': net.get('reserve_requirement'),
    }


def bus_num_to_idx(buses: np.ndarray) -> dict[int, int]:
    """Map raw (possibly non-contiguous) bus numbers to 0-indexed positions."""
    return {int(buses[i, 0]): i for i in range(len(buses))}


def gen_bus_indices(gens: np.ndarray, mapping: dict[int, int]) -> list[int]:
    """Return 0-indexed bus position for each generator row."""
    return [mapping[int(g[0])] for g in gens]


def find_slack_bus(buses: np.ndarray) -> int | None:
    """Return the 0-indexed position of the slack bus (type 3), or None."""
    for i, bus in enumerate(buses):
        if int(bus[1]) == BUS_TYPE_SLACK:
            return i
    return None


def get_generators_at_bus(
    gens: np.ndarray, bus_idx: int, mapping: dict[int, int]
) -> list[int]:
    """Return generator row indices connected to bus_idx (0-indexed)."""
    return [
        i for i, gen in enumerate(gens)
        if mapping[int(gen[0])] == bus_idx
    ]


def get_branch_info(
    branch: np.ndarray, mapping: dict[int, int]
) -> dict[str, Any]:
    """Extract a single branch's parameters keyed by name.

    Columns: 0=from_bus, 1=to_bus, 2=R(pu), 3=X(pu), 4=B(pu),
    5=rateA(MVA), 10=status.
    """
    return {
        'from_bus': mapping[int(branch[0])],
        'to_bus': mapping[int(branch[1])],
        'resistance': float(branch[2]),
        'reactance': float(branch[3]),
        'susceptance': float(branch[4]),
        'rating': float(branch[5]),
        'in_service': int(branch[10]) == 1,
    }


def total_load(buses: np.ndarray) -> float:
    """Total system active load in MW (sum of bus Pd, column 2)."""
    return float(sum(bus[2] for bus in buses))


def to_pu(value_mw: float, base_mva: float) -> float:
    """Convert MW (or MVA / MVAr) to per-unit on the given base."""
    return value_mw / base_mva


def from_pu(value_pu: float, base_mva: float) -> float:
    """Convert per-unit to MW (or MVA / MVAr) on the given base."""
    return value_pu * base_mva
