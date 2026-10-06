#!/usr/bin/env python3
import json
import re
import sys


UNIT_TO_CM = {
    "cm": 1.0,
    "mm": 0.1,
    "m": 100.0,
    "in": 2.54,
    "inch": 2.54,
    "inches": 2.54,
}


def parse_density_table(path):
    with open(path) as f:
        text = f.read()

    rows = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip().strip("*") for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        id_cell = cells[0]
        if not re.fullmatch(r"\d+", id_cell):
            continue
        mat_id = int(id_cell)
        name = cells[1].strip()
        try:
            density = float(cells[2])
        except ValueError:
            continue
        rows[mat_id] = (name, density)
    return rows


def main():
    payload = json.load(sys.stdin)
    state = payload["currentState"]

    volume_raw = float(state["volume_raw"])
    material_id = int(state["material_id"])
    density_table_path = state["density_table_path"]
    coord_unit = str(state["coord_unit"]).lower()

    if coord_unit not in UNIT_TO_CM:
        raise SystemExit(
            f"Unsupported coord_unit {coord_unit!r}; expected one of {sorted(UNIT_TO_CM)}"
        )
    scale = UNIT_TO_CM[coord_unit]
    volume_cm3 = volume_raw * (scale ** 3)

    table = parse_density_table(density_table_path)
    if material_id not in table:
        raise SystemExit(
            f"Material ID {material_id} not in density table at {density_table_path}; "
            f"known IDs: {sorted(table)}"
        )
    material_name, density = table[material_id]
    mass_grams = volume_cm3 * density

    out = {
        "mass_grams": mass_grams,
        "material_name": material_name,
        "density_g_per_cm3": density,
        "volume_cm3": volume_cm3,
    }
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
