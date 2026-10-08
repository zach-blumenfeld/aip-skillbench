"""Wyckoff multiplicities and representative fractional coordinates from a CIF.

Uses the spglib symmetry dataset of the full structure (one Wyckoff letter per
atom), NOT SymmetrizedStructure.wyckoff_symbols (which gives "4a"-style labels
and counts orbits instead of atoms). Needs only pymatgen and sympy.
"""
from collections import Counter, defaultdict

from sympy import Rational

from pymatgen.core import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer


def __FUNCTION_NAME__(filepath):
    """Return {"wyckoff_multiplicity_dict": {letter: atom_count},
    "wyckoff_coordinates_dict": {letter: [x, y, z] as exact-rational strings}}.

    - keys are Wyckoff letters only ("a", "c", "i"), sorted
    - multiplicity = number of atoms in the unit cell carrying that letter
    - coordinates = frac_coords of the FIRST atom (file order) with that letter,
      each as str(Rational(c).limit_denominator(12)), e.g. "0", "1/2", "3/8"
    """
    structure = Structure.from_file(filepath)
    dataset = SpacegroupAnalyzer(structure).get_symmetry_dataset()
    if dataset is None:
        return {"wyckoff_multiplicity_dict": {}, "wyckoff_coordinates_dict": {}}

    wyckoff_letters = [str(w) for w in dataset.wyckoffs]  # one letter per atom

    multiplicity_dict = {
        letter: int(count) for letter, count in sorted(Counter(wyckoff_letters).items())
    }

    wyckoff_sites = defaultdict(list)
    for i, site in enumerate(structure):
        wyckoff_sites[wyckoff_letters[i]].append(site)

    coordinates_dict = {}
    for letter, sites in sorted(wyckoff_sites.items()):
        coords = sites[0].frac_coords
        coordinates_dict[letter] = [
            str(Rational(float(c)).limit_denominator(12)) for c in coords
        ]

    return {
        "wyckoff_multiplicity_dict": multiplicity_dict,
        "wyckoff_coordinates_dict": coordinates_dict,
    }


if __name__ == "__main__":
    import json
    import sys

    for path in sys.argv[1:]:
        print(path, json.dumps(__FUNCTION_NAME__(path)))
