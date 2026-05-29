#!/usr/bin/env python3
"""Helpers for MATPOWER-format power-system network JSON (PGLib-OPF).

Use as a library:

    from network_utils import (
        load_network, build_bus_num_to_idx, find_slack_bus,
        get_generators_at_bus, get_branch_info, total_load,
        to_per_unit, from_per_unit,
    )
    net = load_network('network.json')
    idx = build_bus_num_to_idx(net['bus'])
    slack = find_slack_bus(net['bus'])

Use as a CLI to print a one-shot summary (counts, total load,
reserve totals, slack bus row):

    python network_utils.py network.json
"""
from __future__ import annotations

import json
import sys

import numpy as np

# MATPOWER bus-type codes (column 1 of the bus matrix)
BUS_TYPE_PQ = 1
BUS_TYPE_PV = 2
BUS_TYPE_SLACK = 3

# Default per-unit base power. The actual base is in net['baseMVA'];
# helpers below let the caller pass it explicitly.
DEFAULT_BASEMVA = 100.0


def load_network(filepath: str) -> dict:
    """Load a MATPOWER-format network snapshot from JSON.

    Returns dict with:
        baseMVA              : float  — per-unit base power (MVA)
        bus                  : ndarray (n_bus, ncols), MATPOWER bus matrix.
                               Col 0 = bus number, col 1 = type, col 2 = Pd (MW).
        gen                  : ndarray (n_gen, ncols), MATPOWER gen matrix.
                               Col 0 = bus number.
        branch               : ndarray (n_branch, ncols), MATPOWER branch matrix.
                               Cols 0/1 = from/to bus numbers; 2 = R; 3 = X;
                               4 = B; 5 = rateA (MVA); 10 = in-service.
        gencost              : ndarray (n_gen, ncols), MATPOWER generator-cost matrix.
        reserve_capacity     : ndarray (n_gen,)  — per-generator MW reserve cap
                               (empty if absent in the file).
        reserve_requirement  : float — system MW reserve floor
                               (0.0 if absent in the file).

    Files can be many MB; this uses ``json.load`` so the parse cost is
    O(file) regardless of size — never reach for ``sed`` / ``head`` on
    these files.
    """
    with open(filepath) as f:
        data = json.load(f)
    return {
        'baseMVA': data['baseMVA'],
        'bus': np.array(data['bus']),
        'gen': np.array(data['gen']),
        'branch': np.array(data['branch']),
        'gencost': np.array(data['gencost']),
        'reserve_capacity': np.array(data.get('reserve_capacity', [])),
        'reserve_requirement': data.get('reserve_requirement', 0.0),
    }


def build_bus_num_to_idx(bus: np.ndarray) -> dict:
    """Map MATPOWER bus number (column 0) → 0-indexed row position.

    Bus numbers are NOT contiguous in MATPOWER files (e.g. case300 has
    gaps). Any code that joins a generator or branch back to a bus row
    MUST go through this map — don't use ``bus_number - 1`` as an index.
    """
    return {int(bus[i, 0]): i for i in range(len(bus))}


def find_slack_bus(bus: np.ndarray) -> int | None:
    """Return the 0-indexed row of the slack bus (type code 3), or None."""
    for i, row in enumerate(bus):
        if int(row[1]) == BUS_TYPE_SLACK:
            return i
    return None


def get_generators_at_bus(gen: np.ndarray, bus_idx: int,
                          bus_num_to_idx: dict) -> list:
    """Return indices into ``gen`` of generators connected to a bus row."""
    out = []
    for i, g in enumerate(gen):
        if bus_num_to_idx[int(g[0])] == bus_idx:
            out.append(i)
    return out


def get_branch_info(branch_row, bus_num_to_idx: dict) -> dict:
    """Decode one MATPOWER branch row into a labelled dict.

    Columns used:
        0  from_bus    (bus number; mapped through bus_num_to_idx)
        1  to_bus      (bus number; mapped through bus_num_to_idx)
        2  R           resistance (pu)
        3  X           reactance  (pu)
        4  B           total line charging susceptance (pu)
        5  rateA       MVA thermal rating (used as branch flow limit)
        10 status      1 = in service, 0 = out of service
    """
    return {
        'from_bus': bus_num_to_idx[int(branch_row[0])],
        'to_bus': bus_num_to_idx[int(branch_row[1])],
        'resistance': float(branch_row[2]),
        'reactance': float(branch_row[3]),
        'susceptance': float(branch_row[4]),
        'rating': float(branch_row[5]),
        'in_service': int(branch_row[10]) == 1,
    }


def total_load(bus: np.ndarray) -> float:
    """Sum of active loads Pd (column 2) across all buses, in MW."""
    return float(np.sum(bus[:, 2]))


def to_per_unit(value: float, basemva: float = DEFAULT_BASEMVA) -> float:
    """Convert MW / MVAr / MVA to per-unit on ``basemva``."""
    return value / basemva


def from_per_unit(value_pu: float, basemva: float = DEFAULT_BASEMVA) -> float:
    """Convert per-unit (on ``basemva``) to MW / MVAr / MVA."""
    return value_pu * basemva


def summarize(filepath: str) -> dict:
    """Print and return a one-shot summary of the network file."""
    net = load_network(filepath)
    bus, gen, branch = net['bus'], net['gen'], net['branch']
    summary = {
        'baseMVA': net['baseMVA'],
        'n_bus': int(len(bus)),
        'n_gen': int(len(gen)),
        'n_branch': int(len(branch)),
        'total_load_MW': total_load(bus),
        'reserve_requirement_MW': float(net['reserve_requirement']),
        'reserve_capacity_total_MW': float(net['reserve_capacity'].sum())
            if net['reserve_capacity'].size else 0.0,
        'slack_bus_row': find_slack_bus(bus),
    }
    print(f"baseMVA:                  {summary['baseMVA']}")
    print(f"Buses:                    {summary['n_bus']}")
    print(f"Generators:               {summary['n_gen']}")
    print(f"Branches:                 {summary['n_branch']}")
    print(f"Total load (MW):          {summary['total_load_MW']:.2f}")
    print(f"Reserve requirement (MW): {summary['reserve_requirement_MW']:.2f}")
    print(f"Sum of reserve caps (MW): {summary['reserve_capacity_total_MW']:.2f}")
    slack = summary['slack_bus_row']
    if slack is not None:
        print(f"Slack bus row:            {slack} "
              f"(bus number {int(bus[slack, 0])})")
    else:
        print("Slack bus row:            <none found>")
    return summary


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("usage: network_utils.py NETWORK.json", file=sys.stderr)
        sys.exit(2)
    summarize(sys.argv[1])
