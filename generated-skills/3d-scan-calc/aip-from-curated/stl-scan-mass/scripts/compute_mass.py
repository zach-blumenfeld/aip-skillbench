"""AIP execution step: look up the main part's density and compute its mass.

stdin:  {"currentState": {...}, "assets": {...}, "expects": [...]}
stdout: one JSON object merged over the state.

Required state: main_part_volume (STL units^3), main_part_material_id, density_table_path,
coordinate_unit (mm|cm|m|in|ft|unspecified).
Optional overrides (set by the resolve-material step): material_id_override,
density_override (number), density_unit_override (e.g. "g/cm3"), material_name_override,
review_acknowledged (true = the open issues were reviewed and accepted; status becomes ok).
Upstream mesh_issues (from analyze-mesh) also force a review until acknowledged.

Mass = Volume * Density, after converting the volume from coordinate_unit^3 into the
density table's volume unit. Mass comes out in the density's mass unit. No rounding.
"""

import json
import os
import re
import sys

LENGTH_M = {"mm": 0.001, "cm": 0.01, "dm": 0.1, "m": 1.0, "in": 0.0254, "ft": 0.3048}
LENGTH_ALIASES = {
    "millimeter": "mm", "millimeters": "mm", "millimetre": "mm", "millimetres": "mm",
    "centimeter": "cm", "centimeters": "cm", "centimetre": "cm", "centimetres": "cm",
    "meter": "m", "meters": "m", "metre": "m", "metres": "m",
    "inch": "in", "inches": "in", '"': "in", "foot": "ft", "feet": "ft",
}
# volume token in a density unit -> length unit whose cube it is
VOLUME_TOKENS = {"cc": "cm", "ml": "cm", "l": "dm"}


def norm_length(u):
    u = (u or "").strip().lower()
    u = LENGTH_ALIASES.get(u, u)
    return u if u in LENGTH_M else None


def parse_density_unit(text):
    """'g/cm³' -> ('g', 'cm'); 'kg/m^3' -> ('kg', 'm'); 'g/mL' -> ('g', 'cm')."""
    if not text:
        return None
    t = text.replace("³", "3").replace("^3", "3").replace("**3", "3").replace(" ", "").lower()
    m = re.search(r"\b(mg|g|kg|lb|lbs|oz)/(cc|ml|l|mm3|cm3|dm3|m3|in3|ft3)\b", t)
    if not m:
        return None
    mass, vol = m.group(1), m.group(2)
    length = VOLUME_TOKENS.get(vol, vol[:-1] if vol.endswith("3") else vol)
    return ("lb" if mass == "lbs" else mass), length


def clean(cell):
    return re.sub(r"[*`_]", "", cell).strip()


def parse_table(text):
    """Return (rows, density_unit_text, issues). rows: list of {id, name, density}."""
    issues = []
    lines = [ln.strip() for ln in text.splitlines()]
    if any(ln.startswith("|") for ln in lines):
        raw = [[clean(c) for c in ln.strip("|").split("|")] for ln in lines if ln.startswith("|")]
    else:  # CSV / TSV fallback
        sep = "\t" if any("\t" in ln for ln in lines) else ","
        raw = [[clean(c) for c in ln.split(sep)] for ln in lines if sep in ln]
    raw = [r for r in raw if not all(re.fullmatch(r":?-{2,}:?", c) or c == "" for c in r)]
    if not raw:
        return [], None, ["No table found in density file."]
    header = [h.lower() for h in raw[0]]
    id_col = next((i for i, h in enumerate(header) if re.search(r"\bid\b|identifier|code", h)), None)
    dens_col = next((i for i, h in enumerate(header) if "density" in h), None)
    name_col = next((i for i, h in enumerate(header) if "name" in h and i != id_col), None)
    if name_col is None:
        name_col = next((i for i, h in enumerate(header) if "material" in h and i != id_col), None)
    if id_col is None or dens_col is None:
        return [], None, [f"Could not find ID and density columns in header {raw[0]}."]
    unit_text = raw[0][dens_col]
    if parse_density_unit(unit_text) is None:  # unit not in header: look anywhere in the file
        m = re.search(r"(mg|kg|g|lbs?|oz)\s*/\s*(cc|mL|ml|L|[mcd]?m(?:³|\^3|3)|in(?:³|\^3|3)|ft(?:³|\^3|3))", text)
        unit_text = m.group(0) if m else None
    rows = []
    for r in raw[1:]:
        if len(r) <= max(id_col, dens_col):
            continue
        num = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", r[dens_col].replace(",", ""))
        if not num:
            continue
        rows.append({"id": r[id_col], "name": r[name_col] if name_col is not None and name_col < len(r) else "",
                     "density": float(num.group(0))})
    if not rows:
        issues.append("Density table has no parseable rows.")
    return rows, unit_text, issues


def same_id(a, b):
    a, b = str(a).strip(), str(b).strip()
    try:
        return float(a) == float(b)
    except ValueError:
        return a.lower() == b.lower()


def main():
    payload = json.load(sys.stdin)
    s = payload.get("currentState", payload)
    issues, notes = [], []

    volume = float(s["main_part_volume"])
    mat_id = s.get("material_id_override")
    if mat_id in (None, ""):
        mat_id = s["main_part_material_id"]
    else:
        notes.append(f"Material ID overridden to {mat_id}.")

    rows, unit_text, t_issues = [], None, []
    path = os.path.expanduser(str(s.get("density_table_path", "")))
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            rows, unit_text, t_issues = parse_table(f.read())
    else:
        t_issues = [f"Density table not found at {path!r}."]

    density, name = s.get("density_override"), ""
    if density not in (None, ""):
        density = float(density)
        name = str(s.get("material_name_override", "") or "")
        notes.append(f"Density overridden to {density}.")
        if s.get("density_unit_override"):
            unit_text = s["density_unit_override"]
    else:
        density = None
        issues += t_issues
        match = [r for r in rows if same_id(r["id"], mat_id)]
        if not match:
            issues.append(f"Material ID {mat_id} not found in density table (IDs: {[r['id'] for r in rows]}).")
        else:
            density, name = match[0]["density"], match[0]["name"]
            if len(match) > 1:
                issues.append(f"Material ID {mat_id} appears {len(match)} times in the table; used the first row.")
            if str(mat_id).strip() == "0":
                issues.append("Material ID is 0 (attribute unset); confirm it is a real table entry.")
            if re.search(r"debris|noise|dust|artifact", name, re.I):
                issues.append(f"Main part's material '{name}' is labelled as debris/noise; the main part was probably "
                              "misidentified.")

    unit = parse_density_unit(unit_text)
    if unit is None:
        issues.append(f"Could not determine density unit (found {unit_text!r}); set density_unit_override.")
        mass_unit, dens_len = None, None
    else:
        mass_unit, dens_len = unit

    coord_raw = str(s.get("coordinate_unit", "unspecified"))
    coord = norm_length(coord_raw)
    if coord is None:
        if coord_raw.strip().lower() not in ("", "unspecified", "unknown", "same", "same-as-density"):
            issues.append(f"Unrecognized coordinate_unit {coord_raw!r}; use mm, cm, m, in, ft, or unspecified.")
        elif dens_len:
            notes.append(f"coordinate_unit unspecified: STL coordinates taken to be in {dens_len} "
                         f"(the density table's length unit), so volume is multiplied directly.")
        coord = dens_len

    factor = None
    if coord and dens_len:
        factor = (LENGTH_M[coord] / LENGTH_M[dens_len]) ** 3
    if volume <= 0:
        issues.append("Main part volume is zero or negative.")

    issues += [f"mesh: {m}" for m in s.get("mesh_issues", []) if not m.startswith("Binary parse failed")]
    if str(s.get("mesh_format")) == "ascii" and str(s.get("material_id_override", "")) == "":
        issues.append("mesh: ASCII STL has no attribute bytes, so the material ID (0) is not from the file.")
    acknowledged = s.get("review_acknowledged") is True
    mass = volume * factor * density if (factor is not None and density is not None) else None
    out = {
        "material_id_used": mat_id,
        "material_name": name,
        "density": density,
        "density_unit": f"{mass_unit}/{dens_len}^3" if unit else unit_text,
        "coordinate_unit_used": coord,
        "volume_conversion_factor": factor,
        "volume_in_density_units": volume * factor if factor is not None else None,
        "mass": mass,
        "mass_unit": mass_unit,
        "mass_notes": notes,
        "mass_issues": issues,
        "mass_status": "ok" if (mass is not None and (not issues or acknowledged)) else "needs_review",
    }
    print(json.dumps(out))


if __name__ == "__main__":
    main()
