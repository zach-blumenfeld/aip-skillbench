#!/usr/bin/env python3
"""Lookup table for period search ranges by planet/target type.

Why a script: the workflow lists fixed numeric ranges per planet type.
Hand-applied prose lookups drift; this resolves them deterministically and
returns explicit (min_days, max_days) pairs ready for TLS/BLS power().

Usage:
  python period_range_guide.py --planet-type hot_jupiter
  python period_range_guide.py --planet-type habitable_zone --star sunlike
  python period_range_guide.py --list

Categories follow the curated SKILL.md (hot_jupiter, warm, habitable_zone,
plus shape-matched ranges for stellar rotation / pulsation).
"""

from __future__ import annotations

import argparse
import json
import sys

RANGES: dict[str, tuple[float, float] | dict[str, tuple[float, float]]] = {
    "hot_jupiter": (0.5, 10.0),
    "warm": (10.0, 100.0),
    "habitable_zone": {
        "sunlike": (200.0, 400.0),
        "m_dwarf": (10.0, 50.0),
    },
    "stellar_rotation": (0.1, 100.0),
    "eclipsing_binary": (0.1, 100.0),
    "stellar_pulsation": (0.001, 1.0),
    "general_transit": (0.5, 50.0),
}

EXPECTED_DEPTHS = {
    "hot_jupiter": (0.01, 0.03),
    "super_earth": (0.001, 0.003),
    "earth_sized": (0.0001, 0.001),
}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Resolve period search range by target type.")
    p.add_argument("--planet-type", help="hot_jupiter | warm | habitable_zone | "
                                          "stellar_rotation | stellar_pulsation | "
                                          "eclipsing_binary | general_transit")
    p.add_argument("--star", default=None, help="sunlike | m_dwarf (only for habitable_zone)")
    p.add_argument("--depth-class", default=None,
                   help="hot_jupiter | super_earth | earth_sized (returns expected depth).")
    p.add_argument("--list", action="store_true", help="List all categories and exit.")
    return p.parse_args(argv)


def lookup(planet_type: str, star: str | None) -> tuple[float, float]:
    if planet_type not in RANGES:
        raise SystemExit(
            f"Unknown planet-type {planet_type!r}. Known: {sorted(RANGES.keys())}"
        )
    entry = RANGES[planet_type]
    if isinstance(entry, dict):
        if star is None:
            raise SystemExit(
                f"planet-type {planet_type!r} requires --star (one of {sorted(entry.keys())})."
            )
        if star not in entry:
            raise SystemExit(
                f"Unknown star {star!r} for {planet_type!r}. Known: {sorted(entry.keys())}"
            )
        return entry[star]
    return entry


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    if args.list:
        print(json.dumps({"ranges": RANGES, "expected_depths": EXPECTED_DEPTHS}, indent=2))
        return 0
    if not args.planet_type:
        raise SystemExit("--planet-type is required (or use --list)")

    pmin, pmax = lookup(args.planet_type, args.star)
    out: dict = {
        "planet_type": args.planet_type,
        "star": args.star,
        "period_min_days": pmin,
        "period_max_days": pmax,
    }
    if args.depth_class:
        if args.depth_class not in EXPECTED_DEPTHS:
            raise SystemExit(
                f"Unknown depth-class {args.depth_class!r}. "
                f"Known: {sorted(EXPECTED_DEPTHS.keys())}"
            )
        dmin, dmax = EXPECTED_DEPTHS[args.depth_class]
        out["expected_depth_min"] = dmin
        out["expected_depth_max"] = dmax

    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
