#!/usr/bin/env python3
"""Wyckoff position multiplicity and exact-fraction coordinate extraction.

Reads a CIF file with `pymatgen`, runs space-group symmetry analysis to obtain
Wyckoff letters for each site, counts multiplicities, and converts the
representative atom's fractional coordinates to exact rational strings using
`sympy.Rational.limit_denominator(max_denominator)`.

The denominator cap is the only knob — set it from the task spec
("constrain fractions to have denominators <= N").

Usage:
    from wyckoff_analyze import analyze_wyckoff
    out = analyze_wyckoff("/root/cif_files/FeS2_mp-226.cif", max_denominator=12)
    # {
    #     "wyckoff_multiplicity_dict": {"a": 4, "c": 8},
    #     "wyckoff_coordinates_dict": {
    #         "a": ["0", "1/2", "1/2"],
    #         "c": ["3/8", "1/9", "8/9"],
    #     },
    # }
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict

from pymatgen.core import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from sympy import Rational


def _to_fraction_strings(coords, max_denominator: int):
    return [str(Rational(float(c)).limit_denominator(max_denominator)) for c in coords]


def analyze_wyckoff(filepath: str, max_denominator: int = 12) -> Dict[str, Any]:
    """Return {`wyckoff_multiplicity_dict`, `wyckoff_coordinates_dict`} for `filepath`.

    `wyckoff_multiplicity_dict` maps each Wyckoff letter -> number of atoms in
    the unit cell at that position. `wyckoff_coordinates_dict` maps each
    Wyckoff letter -> list of three exact-fraction strings (the first atom's
    fractional coordinates, rationalized).

    Both sub-dicts are sorted by Wyckoff letter.
    """
    structure = Structure.from_file(filepath)
    sga = SpacegroupAnalyzer(structure)
    dataset = sga.get_symmetry_dataset()

    if dataset is None:
        return {"wyckoff_multiplicity_dict": {}, "wyckoff_coordinates_dict": {}}

    wyckoff_letters = dataset.wyckoffs

    multiplicity_dict = dict(sorted(Counter(wyckoff_letters).items()))

    wyckoff_sites = defaultdict(list)
    for i, site in enumerate(structure):
        wyckoff_sites[wyckoff_letters[i]].append(site)

    coordinates_dict = {
        letter: _to_fraction_strings(sites[0].frac_coords, max_denominator)
        for letter, sites in sorted(wyckoff_sites.items())
    }

    return {
        "wyckoff_multiplicity_dict": multiplicity_dict,
        "wyckoff_coordinates_dict": coordinates_dict,
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filepath", help="Path to the CIF file.")
    parser.add_argument("--max-denominator", type=int, default=12,
                        help="Cap on denominator for fraction approximation (default 12).")
    args = parser.parse_args()
    print(json.dumps(analyze_wyckoff(args.filepath, args.max_denominator), indent=2))
