#!/usr/bin/env python3
"""Wyckoff letters, multiplicities and first-atom rational coordinates from a CIF.

Requires: Python >= 3.10, pymatgen (tested 2025.10.7; pulls in spglib), sympy (tested 1.14.0).

Importable module: copy this file to the solution path the task names
(e.g. /root/workspace/solution.py); the entry point is
    analyze_wyckoff_position_multiplicities_and_coordinates(filepath) -> dict

CLI (verification only; the diagnostics are NOT part of the function's return):
    python wyckoff_solution.py FILE.cif [FILE.cif ...]
        [--max-denominator 12] [--expect FILE.cif '<json dict>']
Prints one JSON object per file with the function result plus diagnostics
(space group, site count, invariant checks as "problems", tolerance sensitivity
as non-fatal "warnings"). Exit code 1 if any problem, read error or --expect
mismatch occurs.
"""
from __future__ import annotations

import warnings
from collections import Counter, defaultdict
from typing import Any

MAX_DENOMINATOR = 12          # task: "constrain fractions to have denominators <= 12"
SYMPREC_DEFAULT = 0.01        # pymatgen/spglib default tolerance
SYMPREC_FALLBACK = 0.1        # retry only if the default finds no symmetry dataset


def _load_structure(filepath: str):
    from pymatgen.core import Structure

    # Keep the cell and site order exactly as written in the file: "first atom"
    # of a Wyckoff letter means first in file order, so never standardize,
    # refine, or reduce to a primitive cell here.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # e.g. "fractional coordinates rounded to ideal values"
        return Structure.from_file(filepath)


def _symmetry_dataset(structure):
    from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

    for symprec in (SYMPREC_DEFAULT, SYMPREC_FALLBACK):
        sga = SpacegroupAnalyzer(structure, symprec=symprec)
        dataset = sga.get_symmetry_dataset()
        if dataset is not None:
            return dataset, sga, symprec
    return None, None, None


def _wyckoff_letters(dataset) -> list[str]:
    # spglib >= 2.5 returns a dataclass; older versions return a dict.
    letters = getattr(dataset, "wyckoffs", None)
    if letters is None:
        letters = dataset["wyckoffs"]
    return [str(x) for x in letters]


def _to_fraction(value: float, max_denominator: int = MAX_DENOMINATOR) -> str:
    from sympy import Rational

    return str(Rational(float(value)).limit_denominator(max_denominator))


def analyze_wyckoff_position_multiplicities_and_coordinates(
    filepath: str, max_denominator: int = MAX_DENOMINATOR
) -> dict[str, dict] | dict[str, Any]:
    """Return {"wyckoff_multiplicity_dict": {letter: n_atoms},
               "wyckoff_coordinates_dict": {letter: [x, y, z] as fraction strings}}."""
    structure = _load_structure(filepath)
    dataset, _, _ = _symmetry_dataset(structure)
    if dataset is None:
        return {"wyckoff_multiplicity_dict": {}, "wyckoff_coordinates_dict": {}}

    letters = _wyckoff_letters(dataset)  # one letter per site, in file order

    multiplicity_dict = dict(sorted(Counter(letters).items()))

    sites_by_letter = defaultdict(list)
    for i, site in enumerate(structure):
        sites_by_letter[letters[i]].append(site)

    coordinates_dict = {
        letter: [_to_fraction(c, max_denominator) for c in sites[0].frac_coords]
        for letter, sites in sorted(sites_by_letter.items())
    }

    return {
        "wyckoff_multiplicity_dict": multiplicity_dict,
        "wyckoff_coordinates_dict": coordinates_dict,
    }


# ---------------------------------------------------------------- CLI checks
def _diagnose(filepath: str, max_denominator: int) -> dict:
    from fractions import Fraction

    result = analyze_wyckoff_position_multiplicities_and_coordinates(filepath, max_denominator)
    structure = _load_structure(filepath)
    dataset, sga, symprec = _symmetry_dataset(structure)
    mult = result["wyckoff_multiplicity_dict"]
    coords = result["wyckoff_coordinates_dict"]
    problems = []
    if dataset is None:
        problems.append("no symmetry dataset even at symprec=0.1; result is empty")
    else:
        if sum(mult.values()) != len(structure):
            problems.append(f"multiplicities sum {sum(mult.values())} != {len(structure)} sites")
        if set(mult) != set(coords):
            problems.append("multiplicity and coordinate dicts have different letters")
        for letter, xyz in coords.items():
            if not (len(letter) == 1 and letter.isalpha() and letter.islower()):
                problems.append(f"key {letter!r} is not a bare Wyckoff letter")
            if len(xyz) != 3:
                problems.append(f"{letter}: expected 3 coordinates, got {len(xyz)}")
            for s in xyz:
                if not isinstance(s, str) or Fraction(s).denominator > max_denominator:
                    problems.append(f"{letter}: bad coordinate {s!r}")
    # Non-fatal: does a looser tolerance find a different (higher) space group?
    warnings_ = []
    loose_symbol = None
    if sga is not None:
        from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

        try:
            loose = SpacegroupAnalyzer(structure, symprec=SYMPREC_FALLBACK)
            loose_symbol = f"{loose.get_space_group_symbol()} (#{loose.get_space_group_number()})"
        except Exception:  # spglib found nothing at the loose tolerance
            loose_symbol = None
        if symprec == SYMPREC_DEFAULT and loose_symbol and loose.get_space_group_number() != sga.get_space_group_number():
            warnings_.append(
                f"tolerance-sensitive: symprec={SYMPREC_DEFAULT} gives {sga.get_space_group_symbol()}, "
                f"symprec={SYMPREC_FALLBACK} gives {loose_symbol}"
            )
    return {
        "file": filepath,
        "result": result,
        "diagnostics": {
            "n_sites": len(structure),
            "space_group": f"{sga.get_space_group_symbol()} (#{sga.get_space_group_number()})" if sga else None,
            "symprec_used": symprec,
            "space_group_at_symprec_0.1": loose_symbol,
            "problems": problems,
            "warnings": warnings_,
        },
    }


def main() -> int:
    import argparse
    import json

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="+", help="CIF files to analyze")
    p.add_argument("--max-denominator", type=int, default=MAX_DENOMINATOR)
    p.add_argument("--expect", nargs=2, action="append", default=[], metavar=("FILE", "JSON"),
                   help="compare the result for FILE with an expected JSON dict (e.g. the task's example)")
    args = p.parse_args()

    failed = False
    for fp in args.files:
        try:
            report = _diagnose(fp, args.max_denominator)
        except Exception as exc:  # unreadable/unsupported file
            report = {"file": fp, "error": f"{type(exc).__name__}: {exc}"}
            failed = True
        else:
            failed |= bool(report["diagnostics"]["problems"])
        print(json.dumps(report))

    for fp, expected_json in args.expect:
        expected = json.loads(expected_json)
        got = analyze_wyckoff_position_multiplicities_and_coordinates(fp, args.max_denominator)
        ok = got == expected
        failed |= not ok
        print(json.dumps({"expect_check": fp, "match": ok, "got": got, "expected": expected}))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
