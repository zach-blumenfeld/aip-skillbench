#!/usr/bin/env python3
"""AIP execution step: convert the raw STL volume into cm^3 using the declared
coordinate unit, then multiply by density (g/cm^3) to produce mass in grams."""
import json
import sys

# Linear factor from the named unit to centimeters. Volume factor is this cubed.
UNIT_TO_CM = {
    "mm": 0.1,
    "cm": 1.0,
    "m": 100.0,
    "in": 2.54,
    "inch": 2.54,
}


def main() -> None:
    payload = json.load(sys.stdin)
    state = payload.get("currentState", {})

    volume_raw = float(state["main_part_volume"])
    unit = str(state["stl_coord_unit"]).strip().lower()
    density = float(state["density_g_per_cm3"])

    if unit not in UNIT_TO_CM:
        raise SystemExit(
            f"Unknown stl_coord_unit {unit!r}; expected one of {sorted(UNIT_TO_CM)}"
        )

    linear = UNIT_TO_CM[unit]
    volume_cm3 = volume_raw * (linear ** 3)
    mass_g = volume_cm3 * density

    out = {
        "volume_cm3": volume_cm3,
        "mass_g": mass_g,
    }
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
