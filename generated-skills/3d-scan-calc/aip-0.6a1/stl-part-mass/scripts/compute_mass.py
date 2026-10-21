"""Step compute-mass: Mass = Volume * Density, written as the JSON report.

stdin:  {"state": {"main_part_volume", "material_id", "density", "density_unit",
                   "coordinate_units", "report_path"}, "assets", "expects"}
stdout: {"main_part_mass", "mass_report"}

coordinate_units "same_as_table" multiplies directly (no conversion). Any explicit
unit converts the volume to cm^3 and the density to g/cm^3, giving mass in grams.
"""

import json
import os
import sys

CM_PER_UNIT = {"millimeters": 0.1, "centimeters": 1.0, "meters": 100.0, "inches": 2.54}


def density_g_per_cm3(density, unit_text):
    u = unit_text.lower().replace(" ", "").replace("³", "3").replace("^", "")
    if "kg/m3" in u:
        return density / 1000.0
    if "g/mm3" in u:
        return density * 1000.0
    if "g/cm3" in u or "g/cc" in u or "g/ml" in u:
        return density
    sys.exit(f"Cannot convert density unit {unit_text!r} to g/cm^3; use coordinate_units same_as_table or extend this script.")


def main():
    s = json.load(sys.stdin)["state"]
    units = s["coordinate_units"]
    if units == "same_as_table":
        mass = s["main_part_volume"] * s["density"]
    elif units in CM_PER_UNIT:
        volume_cm3 = s["main_part_volume"] * CM_PER_UNIT[units] ** 3
        mass = volume_cm3 * density_g_per_cm3(s["density"], s["density_unit"])
    else:
        sys.exit(f"Unknown coordinate_units {units!r}; expected same_as_table or one of {sorted(CM_PER_UNIT)}")

    report = {"main_part_mass": round(mass, 4), "material_id": int(s["material_id"])}
    path = s["report_path"]
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(report, f, indent=1)
        f.write("\n")
    json.dump({"main_part_mass": report["main_part_mass"], "mass_report": report}, sys.stdout)


if __name__ == "__main__":
    main()
