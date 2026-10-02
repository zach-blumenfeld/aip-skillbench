#!/usr/bin/env python3
"""Parse the material density table, compute mass = volume * density, write JSON report.

The density table is a markdown file with rows like:
    | **10** | Standard Steel | 7.85 | Common structural steel. |
The first bolded integer column is the material ID; the third column is density (g/cm^3).

Units flow through untouched: if the STL coordinates are cm and the table is g/cm^3, mass is g.
The skill does no unit conversion — the caller is responsible for matching units.

stdin:  {"currentState": {"main_part_volume": float, "material_id": int,
                          "density_table_path": str, "output_path": str, ...},
         "assets": {...}, "expects": {...}}
stdout: {"main_part_mass": float, "report_path": str, "density": float}
"""
import json
import re
import sys


def parse_density_table(path):
    """Return {material_id: density} from a markdown table.

    Accepts rows where the ID cell is bolded (`**42**`) or plain (`42`) and the
    density cell is any float. Non-data rows (header, separator, prose) are skipped.
    """
    table = {}
    with open(path) as f:
        for raw in f:
            line = raw.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 3:
                continue
            id_match = re.match(r"^\**\s*(\d+)\s*\**$", cells[0])
            if not id_match:
                continue
            try:
                density = float(re.sub(r"[^\d.\-eE]", "", cells[2]))
            except ValueError:
                continue
            table[int(id_match.group(1))] = density
    return table


payload = json.load(sys.stdin)
state = payload["currentState"]

volume = float(state["main_part_volume"])
material_id = int(state["material_id"])
density_table_path = state["density_table_path"]
output_path = state["output_path"]

table = parse_density_table(density_table_path)
if material_id not in table:
    sys.stderr.write(
        f"Material ID {material_id} not found in density table {density_table_path}. "
        f"Known IDs: {sorted(table)}\n"
    )
    sys.exit(1)

density = table[material_id]
mass = volume * density

report = {"main_part_mass": mass, "material_id": material_id}
with open(output_path, "w") as f:
    json.dump(report, f, indent=2)

json.dump(
    {"main_part_mass": mass, "report_path": output_path, "density": density},
    sys.stdout,
)
