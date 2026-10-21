"""AIP step `install-solution`: write the solution module and run it over every CIF.

stdin:  {"state": {"cif_dir": str, "solution_path": str}, "assets": {...}, "expects": [...]}
stdout: {"solution_written", "batch_results", "batch_errors", "batch_warnings"}

Copies wyckoff_solution.py (next to this script) to solution_path, imports the copy that was
actually written, and calls its entry function on every *.cif in cif_dir. Per-file problems
are reported, not raised, so the review step can judge them. Exits non-zero only when the
solution cannot be written or imported.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
import warnings
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ next to the installed solution

ENTRY = "analyze_wyckoff_position_multiplicities_and_coordinates"
LETTER = re.compile(r"^[a-zA-Z]$")
FRACTION = re.compile(r"^-?\d+(/\d+)?$")


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("wyckoff_solution_installed", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def declared_space_group(cif: Path) -> str | None:
    """Space group the CIF itself declares (SHELX/pymatgen tags), for comparison only."""
    try:
        from pymatgen.io.cif import CifParser

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            block = next(iter(CifParser(str(cif)).as_dict().values()))
        for tag in ("_space_group_name_H-M_alt", "_symmetry_space_group_name_H-M"):
            if tag in block:
                return str(block[tag]).strip().strip("'\"")
    except Exception:
        return None
    return None


def detected_space_group(cif: Path, module) -> dict:
    from pymatgen.core import Structure
    from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

    reader = getattr(module, "_read_structure", lambda p: Structure.from_file(p))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        s = reader(str(cif))
        sga = SpacegroupAnalyzer(s)
        return {
            "symbol": sga.get_space_group_symbol(),
            "number": sga.get_space_group_number(),
            "num_sites": len(s),
            "is_ordered": s.is_ordered,
        }


def check_output(name: str, out, info: dict, errors: list, warns: list) -> None:
    if not isinstance(out, dict) or set(out) != {"wyckoff_multiplicity_dict", "wyckoff_coordinates_dict"}:
        errors.append({"file": name, "error": f"unexpected return shape: {out!r}"[:300]})
        return
    mult, coords = out["wyckoff_multiplicity_dict"], out["wyckoff_coordinates_dict"]
    if not mult:
        errors.append({"file": name, "error": "empty result: spglib found no symmetry dataset"})
        return
    if set(mult) != set(coords):
        errors.append({"file": name, "error": "multiplicity and coordinate dicts have different letters"})
    for k, v in mult.items():
        if not LETTER.match(str(k)):
            errors.append({"file": name, "error": f"key {k!r} is not a bare Wyckoff letter"})
        if not isinstance(v, int) or v < 1:
            errors.append({"file": name, "error": f"multiplicity for {k!r} is not a positive int: {v!r}"})
    for k, v in coords.items():
        if not (isinstance(v, list) and len(v) == 3 and all(isinstance(c, str) and FRACTION.match(c) for c in v)):
            errors.append({"file": name, "error": f"coordinates for {k!r} are not 3 fraction strings: {v!r}"})
            continue
        if any(int(c.split("/")[1]) > 12 for c in v if "/" in c):
            errors.append({"file": name, "error": f"denominator > 12 in {k!r}: {v}"})
        if "1" in v:
            warns.append({"file": name, "warning": f"letter {k!r} has a coordinate that rounds to 1 "
                          f"(fractional coord just below 1.0): {v}. Reference convention keeps it as '1'."})
    if info:
        if sum(mult.values()) != info["num_sites"]:
            errors.append({"file": name, "error": f"multiplicities sum to {sum(mult.values())}, "
                           f"cell has {info['num_sites']} atoms"})
        if info["number"] == 1:
            warns.append({"file": name, "warning": "spglib found only P1 at symprec=0.01; every atom is 'a'. "
                          "Correct for a truly triclinic P1 structure, suspicious for noisy coordinates."})
        if not info["is_ordered"]:
            warns.append({"file": name, "warning": "structure has partial occupancies (disordered sites)."})


def main() -> None:
    state = json.load(sys.stdin).get("state", {})
    cif_dir = Path(state.get("cif_dir", ""))
    solution_path = Path(state.get("solution_path", ""))
    if not str(state.get("solution_path", "")).strip():
        fail("solution_path is empty")

    src = Path(__file__).resolve().parent / "wyckoff_solution.py"
    try:
        solution_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, solution_path)
        module = load_module(solution_path)
        entry = getattr(module, ENTRY)
    except Exception as exc:  # noqa: BLE001
        fail(f"could not install/import solution at {solution_path}: {exc!r}")

    errors: list = []
    warns: list = []
    results: dict = {}
    cifs = sorted(p for p in cif_dir.glob("*") if p.is_file() and p.suffix.lower() == ".cif") if cif_dir.is_dir() else []
    if not cifs:
        errors.append({"file": str(cif_dir), "error": "no .cif files found (wrong cif_dir?)"})

    for cif in cifs:
        name = cif.name
        try:
            info = detected_space_group(cif, module)
        except Exception as exc:  # noqa: BLE001
            info = {}
            warns.append({"file": name, "warning": f"space-group probe failed: {exc!r}"[:300]})
        try:
            out = entry(str(cif))
        except Exception as exc:  # noqa: BLE001
            errors.append({"file": name, "error": f"{type(exc).__name__}: {exc}"[:300]})
            results[name] = {"output": None, **info, "declared_space_group": declared_space_group(cif)}
            continue
        results[name] = {"output": out, **info, "declared_space_group": declared_space_group(cif)}
        check_output(name, out, info, errors, warns)

    print(json.dumps({
        "solution_written": str(solution_path),
        "batch_results": results,
        "batch_errors": errors,
        "batch_warnings": warns,
    }))


if __name__ == "__main__":
    main()
