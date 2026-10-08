"""Step `analyze-cifs`: run the canonical Wyckoff analysis on every input CIF.

The analysis code is the pack's solution template itself (assets/
solution_template.py), so what is previewed here is exactly what the written
solution will return. Adds per-file diagnostics: space group, site count,
order/disorder, CIF-parser warnings, and symmetry-tolerance sensitivity.
"""
import sys
sys.dont_write_bytecode = True  # keep the skill folder free of __pycache__

import os

from _common import (call_quietly, emit, expand_cif_paths, fail,
                     load_module_from_source, read_payload, render,
                     template_source)


def main():
    state, assets = read_payload()
    paths = state.get("cif_paths")
    if isinstance(paths, str):
        paths = [paths]
    if not paths:
        fail("cif_paths is empty: give CIF files or a directory of CIFs")
    files, missing = expand_cif_paths(paths)
    if not files:
        fail("no CIF files found", missing=missing)

    try:
        from pymatgen.core import Structure
        from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
    except ImportError as exc:
        fail(f"pymatgen is not importable in this python ({exc}); it must provide pymatgen and sympy")

    mod = load_module_from_source(render(template_source(assets), "analyze"))

    analyses, n_errors = [], 0
    for path in files:
        rec = {"file": os.path.basename(path), "path": path, "notes": []}
        try:
            result, parse_warnings = call_quietly(mod.analyze, path)
            rec.update(result)
            structure, _ = call_quietly(Structure.from_file, path)
            sga = SpacegroupAnalyzer(structure)
            rec["formula"] = structure.composition.reduced_formula
            rec["num_sites"] = len(structure)
            rec["spacegroup_symbol"] = sga.get_space_group_symbol()
            rec["spacegroup_number"] = sga.get_space_group_number()
            rec["is_ordered"] = bool(structure.is_ordered)
            rec["parse_warnings"] = parse_warnings

            mult = result["wyckoff_multiplicity_dict"]
            if not mult:
                rec["notes"].append("spglib returned no symmetry dataset; result is empty dicts by design")
            elif sum(mult.values()) != len(structure):
                rec["notes"].append(f"multiplicities sum to {sum(mult.values())}, not {len(structure)} sites")
            if not structure.is_ordered:
                rec["notes"].append("structure has partial occupancies; letters come from spglib on the site species as parsed")
            loose = SpacegroupAnalyzer(structure, symprec=0.1).get_space_group_symbol()
            if loose != rec["spacegroup_symbol"]:
                rec["notes"].append(
                    f"tolerance-sensitive: symprec=0.01 (default, used) gives {rec['spacegroup_symbol']}, "
                    f"symprec=0.1 gives {loose}; keep the default unless the task names a tolerance")
            if any(c == "1" for xyz in result["wyckoff_coordinates_dict"].values() for c in xyz):
                rec["notes"].append("a coordinate near 1.0 rounds to \"1\" (kept as-is; the convention does not wrap to 0)")
        except Exception as exc:  # keep going so one bad file does not hide the rest
            n_errors += 1
            rec["error"] = f"{type(exc).__name__}: {exc}"
        analyses.append(rec)

    lines = []
    for r in analyses:
        if "error" in r:
            lines.append(f"{r['file']}: ERROR {r['error']}")
        else:
            lines.append(f"{r['file']}: {r['formula']} {r['spacegroup_symbol']} (#{r['spacegroup_number']}), "
                         f"{r['num_sites']} sites, multiplicities {r['wyckoff_multiplicity_dict']}")
    emit({
        "cif_files": files,
        "missing_paths": missing,
        "analyses": analyses,
        "analysis_errors": n_errors,
        "analysis_summary": "\n".join(lines),
    })


if __name__ == "__main__":
    main()
