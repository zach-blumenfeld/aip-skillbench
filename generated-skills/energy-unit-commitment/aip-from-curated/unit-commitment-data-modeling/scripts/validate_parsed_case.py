#!/usr/bin/env python3
"""Parser-level validation for a normalized UC case dict.

Usage:

    # As a CLI: reads JSON, prints findings, exits 0 on clean / 1 on error.
    python validate_parsed_case.py path/to/case.json

    # As a library:
    from validate_parsed_case import validate_case
    errors = validate_case(case)  # list[str]; empty means clean

The case dict is the normalized representation produced by the parsing
workflow. Expected shape (all keys optional unless required by the
checks they enable):

    {
        "T": int,                          # number of periods
        "periods": list[Any],              # length T
        "thermal_names": list[str],
        "renewable_names": list[str],
        "demand": list[float],             # length T
        "reserve_requirement": list[float],  # length T
        "thermal": {                       # by thermal name
            "<name>": {
                "pmin": float,
                "pmax": float,
                "initial_status": int,     # 0/1
                "initial_output": float,
                "min_up": int,
                "min_down": int,
                "startup_tiers": [ {"lag": float, "cost": float}, ... ],
                "production_curve": [ {"mw": float, "cost": float}, ... ],
            }
        },
        "renewable_min": {"<name>": [float, ...]},  # each list length T
        "renewable_max": {"<name>": [float, ...]},  # each list length T
    }

Errors are returned, not raised — the agent decides whether to abort
or repair. The checks mirror the original SKILL.md's validation block
plus the structural integrity checks (duplicate IDs, mismatched lengths,
missing required fields, nonmonotone startup lags, inconsistent initial
conditions).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any


def _finite(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _all_finite(seq: Any) -> bool:
    try:
        return all(_finite(v) for v in seq)
    except TypeError:
        return False


def validate_case(case: dict) -> list[str]:
    """Run all parser-level checks. Returns a list of error messages."""
    errors: list[str] = []

    T = case.get("T")
    if not isinstance(T, int) or T <= 0:
        errors.append("missing or invalid 'T' (must be positive int)")

    periods = case.get("periods")
    if periods is not None and isinstance(T, int) and len(periods) != T:
        errors.append(f"len(periods)={len(periods)} != T={T}")

    demand = case.get("demand")
    if demand is None:
        errors.append("missing 'demand'")
    else:
        if isinstance(T, int) and len(demand) != T:
            errors.append(f"len(demand)={len(demand)} != T={T}")
        if not _all_finite(demand):
            errors.append("'demand' contains non-finite values")

    reserve = case.get("reserve_requirement")
    if reserve is None:
        errors.append("missing 'reserve_requirement'")
    else:
        if isinstance(T, int) and len(reserve) != T:
            errors.append(
                f"len(reserve_requirement)={len(reserve)} != T={T}"
            )
        if not _all_finite(reserve):
            errors.append("'reserve_requirement' contains non-finite values")

    for key in ("thermal_names", "renewable_names"):
        names = case.get(key, [])
        if len(set(names)) != len(names):
            seen, dups = set(), []
            for n in names:
                if n in seen:
                    dups.append(n)
                seen.add(n)
            errors.append(f"duplicate IDs in {key}: {sorted(set(dups))}")

    thermal = case.get("thermal") or {}
    for name, params in thermal.items():
        pmin = params.get("pmin")
        pmax = params.get("pmax")
        if pmin is None or pmax is None:
            errors.append(f"thermal[{name}]: missing pmin or pmax")
        elif not (_finite(pmin) and _finite(pmax)):
            errors.append(f"thermal[{name}]: pmin/pmax not finite")
        elif pmin > pmax:
            errors.append(f"thermal[{name}]: pmin={pmin} > pmax={pmax}")

        tiers = params.get("startup_tiers")
        if tiers is not None:
            if len(tiers) < 1:
                errors.append(f"thermal[{name}]: startup_tiers is empty")
            lags = [t.get("lag") for t in tiers]
            if any(l is None or not _finite(l) for l in lags):
                errors.append(
                    f"thermal[{name}]: startup_tiers has missing/non-finite lag"
                )
            elif sorted(lags) != list(sorted(set(lags))):
                errors.append(
                    f"thermal[{name}]: startup_tiers lags have duplicates"
                )

        curve = params.get("production_curve")
        if curve is not None:
            if len(curve) < 2:
                errors.append(
                    f"thermal[{name}]: production_curve needs >= 2 points"
                )
            mws = [p.get("mw") for p in curve]
            if len(set(mws)) != len(mws):
                errors.append(
                    f"thermal[{name}]: production_curve has repeated mw points"
                )

        init_status = params.get("initial_status")
        init_output = params.get("initial_output")
        if init_status is not None and init_output is not None:
            if init_status == 0 and init_output not in (0, 0.0):
                errors.append(
                    f"thermal[{name}]: initial_status=0 but initial_output={init_output}"
                )
            if (
                init_status == 1
                and pmin is not None
                and _finite(init_output)
                and float(init_output) < float(pmin) - 1e-9
            ):
                errors.append(
                    f"thermal[{name}]: initial_status=1 but initial_output={init_output} < pmin={pmin}"
                )

    rmin = case.get("renewable_min") or {}
    rmax = case.get("renewable_max") or {}
    for name in set(rmin) | set(rmax):
        lo = rmin.get(name)
        hi = rmax.get(name)
        if lo is None or hi is None:
            errors.append(f"renewable[{name}]: missing min or max series")
            continue
        if isinstance(T, int):
            if len(lo) != T:
                errors.append(f"renewable[{name}]: len(min)={len(lo)} != T={T}")
            if len(hi) != T:
                errors.append(f"renewable[{name}]: len(max)={len(hi)} != T={T}")
        if not (_all_finite(lo) and _all_finite(hi)):
            errors.append(f"renewable[{name}]: min/max contains non-finite values")
        if len(lo) == len(hi) and any(
            float(a) > float(b) + 1e-9 for a, b in zip(lo, hi)
        ):
            errors.append(f"renewable[{name}]: min > max in at least one period")

    return errors


def _main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: validate_parsed_case.py <case.json>", file=sys.stderr)
        return 2
    case = json.loads(Path(argv[1]).read_text())
    errors = validate_case(case)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        print(f"FAIL: {len(errors)} error(s)")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
