#!/usr/bin/env python3
"""Print a one-screen summary of a MATPOWER-format network file.

Usage:
    python scripts/summarize_network.py <path-to-network.json>

Use this for first-look orientation instead of `head`/`sed`/`cat`. Reports
counts, total load, baseMVA, slack bus, and whether reserve fields are
present.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running as `python scripts/summarize_network.py` from skill root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from network_utils import (  # noqa: E402
    bus_num_to_idx,
    find_slack_bus,
    load_network,
    total_load,
)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: summarize_network.py <network.json>", file=sys.stderr)
        return 2

    net = load_network(argv[1])
    bus = net["bus"]
    gen = net["gen"]
    branch = net["branch"]

    slack_row = find_slack_bus(bus)
    slack_num = int(bus[slack_row, 0]) if slack_row is not None else None

    idx_map = bus_num_to_idx(bus)
    bus_numbers = sorted(idx_map)
    contiguous = bus_numbers == list(range(bus_numbers[0], bus_numbers[-1] + 1))

    print(f"file:                 {argv[1]}")
    print(f"baseMVA:              {net['baseMVA']}")
    print(f"buses:                {len(bus)}")
    print(f"generators:           {len(gen)}")
    print(f"branches:             {len(branch)}")
    print(f"total load (MW):      {total_load(bus):.1f}")
    print(f"slack bus number:     {slack_num}")
    print(f"bus number range:     {bus_numbers[0]}..{bus_numbers[-1]}")
    print(f"bus numbers contig.:  {contiguous}")
    print(f"reserve_capacity:     {'present' if net['reserve_capacity'] is not None else 'absent'}")
    print(f"reserve_requirement:  {net['reserve_requirement']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
