"""Wyckoff multiplicities and first-atom coordinates from a CIF file.

Installed verbatim as the task's solution module (e.g. /root/workspace/solution.py).
Needs only pymatgen (which pulls in spglib) and sympy.

Method (pymatgen skill, references/wyckoff-positions-from-cif.md):
- Read the full unit cell with Structure.from_file (applies the CIF's symmetry ops); only if
  that fails, retry with CifParser(occupancy_tolerance=1.05) for SHELX-rounded occupancies.
- Take the spglib dataset from SpacegroupAnalyzer(structure).get_symmetry_dataset();
  dataset.wyckoffs holds one International Tables letter per atom of the structure.
  Do NOT use get_symmetrized_structure().wyckoff_symbols: those are "4a"-style labels,
  one per orbit, not letters per atom.
- multiplicity[letter] = number of atoms carrying that letter in the cell.
- coordinates[letter] = frac_coords of the FIRST atom (structure order) with that letter,
  each as str(sympy.Rational(c).limit_denominator(12)).
"""

from __future__ import annotations

import warnings
from collections import Counter, defaultdict
from typing import Any

from pymatgen.core import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from sympy import Rational

MAX_DENOMINATOR = 12
# Default spglib tolerance first (gives the reference answers); the looser one is only a
# fallback for noisy experimental CIFs where the default finds no dataset at all.
SYMPRECS = (0.01, 0.1)


def _symmetry_dataset(structure: Structure):
    for symprec in SYMPRECS:
        try:
            dataset = SpacegroupAnalyzer(structure, symprec=symprec).get_symmetry_dataset()
        except Exception:
            dataset = None
        if dataset is not None:
            return dataset
    return None


def _read_structure(filepath: str) -> Structure:
    try:
        return Structure.from_file(filepath)  # full cell, CIF symmetry operations applied
    except ValueError:
        # SHELX-rounded occupancies (e.g. 1.04) exceed pymatgen's default tolerance of 1.0 and
        # the parser then reports "Invalid CIF file with no structures!". Keep the full cell.
        from pymatgen.io.cif import CifParser

        return CifParser(filepath, occupancy_tolerance=1.05).parse_structures(primitive=False)[0]


def _to_fraction(value: float) -> str:
    return str(Rational(float(value)).limit_denominator(MAX_DENOMINATOR))


def analyze_wyckoff_position_multiplicities_and_coordinates(
    filepath: str,
) -> dict[str, dict] | dict[str, Any]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # pymatgen CIF parser chatter
        structure = _read_structure(filepath)
        dataset = _symmetry_dataset(structure)

    if dataset is None:
        return {"wyckoff_multiplicity_dict": {}, "wyckoff_coordinates_dict": {}}

    wyckoff_letters = list(dataset.wyckoffs)  # one letter per atom, structure order

    multiplicity_dict = {k: int(v) for k, v in sorted(Counter(wyckoff_letters).items())}

    wyckoff_sites = defaultdict(list)
    for i, site in enumerate(structure):
        wyckoff_sites[wyckoff_letters[i]].append(site)

    coordinates_dict = {
        letter: [_to_fraction(c) for c in sites[0].frac_coords]
        for letter, sites in sorted(wyckoff_sites.items())
    }

    return {
        "wyckoff_multiplicity_dict": multiplicity_dict,
        "wyckoff_coordinates_dict": coordinates_dict,
    }


if __name__ == "__main__":
    import json
    import sys

    for path in sys.argv[1:]:
        print(path, json.dumps(analyze_wyckoff_position_multiplicities_and_coordinates(path)))
