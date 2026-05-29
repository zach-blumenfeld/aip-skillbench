"""MATPOWER-format network data utilities.

All functions operate on the dict returned by `load_network`. Numeric data is
returned as numpy arrays so downstream OPF/power-flow code can index without
re-conversion.

Column conventions (0-indexed) follow the MATPOWER manual:

  bus    : [bus_i, bus_type, Pd, Qd, Gs, Bs, area, Vm, Va, baseKV, zone,
            Vmax, Vmin]
  gen    : [bus, Pg, Qg, Qmax, Qmin, Vg, mBase, status, Pmax, Pmin, ...]
  branch : [fbus, tbus, r, x, b, rateA, rateB, rateC, ratio, angle,
            status, angmin, angmax]
  gencost: [model, startup, shutdown, n, c_(n-1), ..., c_0]

Reserve fields (`reserve_capacity`, `reserve_requirement`) are PGLib /
benchmark extensions, not standard MATPOWER. The loader returns None when
they are missing.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


def load_network(filepath: str | Path) -> dict[str, Any]:
    """Load a MATPOWER-format JSON file into numpy arrays.

    Returns a dict with keys: baseMVA, bus, gen, branch, gencost,
    reserve_capacity, reserve_requirement. The two reserve fields are None
    when not present in the source file.

    Always use this loader. Never read large network JSON with `head`, `sed`,
    or similar tools — json.load is fast even for multi-MB files and gives
    you parsed structure in one shot.
    """
    with open(filepath) as f:
        data = json.load(f)

    return {
        "baseMVA": data["baseMVA"],
        "bus": np.array(data["bus"]),
        "gen": np.array(data["gen"]),
        "branch": np.array(data["branch"]),
        "gencost": np.array(data["gencost"]),
        "reserve_capacity": (
            np.array(data["reserve_capacity"])
            if "reserve_capacity" in data
            else None
        ),
        "reserve_requirement": data.get("reserve_requirement"),
    }


def bus_num_to_idx(bus: np.ndarray) -> dict[int, int]:
    """Map bus number (column 0) to 0-indexed row position.

    Bus numbers in MATPOWER files are NOT guaranteed to be contiguous or
    1-indexed. Always go through this mapping before indexing into the bus
    array or matching gen/branch rows to bus rows.
    """
    return {int(bus[i, 0]): i for i in range(len(bus))}


def find_slack_bus(bus: np.ndarray) -> int | None:
    """Return the 0-indexed row of the slack bus (bus type code 3).

    Returns None if no slack bus is present (a malformed network — DC-OPF
    requires a reference bus).
    """
    for i, row in enumerate(bus):
        if int(row[1]) == 3:
            return i
    return None


def get_generators_at_bus(
    gen: np.ndarray, bus_idx: int, idx_map: dict[int, int]
) -> list[int]:
    """Return generator row indices connected to a 0-indexed bus position."""
    out: list[int] = []
    for i, row in enumerate(gen):
        if idx_map[int(row[0])] == bus_idx:
            out.append(i)
    return out


def get_branch_info(
    branch_row: np.ndarray, idx_map: dict[int, int]
) -> dict[str, Any]:
    """Decode a single branch row into a named-field dict.

    `from_bus` and `to_bus` are 0-indexed positions (already mapped through
    idx_map), not raw bus numbers.
    """
    return {
        "from_bus": idx_map[int(branch_row[0])],
        "to_bus": idx_map[int(branch_row[1])],
        "resistance": float(branch_row[2]),
        "reactance": float(branch_row[3]),
        "susceptance": float(branch_row[4]),
        "rating": float(branch_row[5]),
        "in_service": int(branch_row[10]) == 1,
    }


def total_load(bus: np.ndarray) -> float:
    """Sum bus column 2 (Pd) — total active-power system load in MW."""
    return float(np.sum(bus[:, 2]))


def find_branch(
    branch: np.ndarray,
    from_bus_number: int,
    to_bus_number: int,
) -> int | None:
    """Return the 0-indexed row of the branch connecting two raw bus numbers.

    Matches in either direction (fbus->tbus or tbus->fbus). Returns None if
    no matching branch exists. Useful when a task specifies a line by its
    endpoint bus numbers (e.g., "bus 64 to bus 1501") and you need the row
    to read or perturb its rating.
    """
    a, b = int(from_bus_number), int(to_bus_number)
    for i, row in enumerate(branch):
        f, t = int(row[0]), int(row[1])
        if (f, t) == (a, b) or (f, t) == (b, a):
            return i
    return None
