#!/usr/bin/env python3
"""
Wyckoff position analysis from a CIF (or any pymatgen-readable structure file).

The correct workflow lives here so callers don't reinvent it and don't fall
into the `get_symmetrized_structure().wyckoff_symbols` trap (which returns
`4a` / `8c` style symbols and one entry per orbit, not per atom).

Output contract — produced by `analyze_wyckoff_position_multiplicities_and_coordinates`:

    {
        "wyckoff_multiplicity_dict": {letter: total atoms on that letter, ...},
        "wyckoff_coordinates_dict":   {letter: [str(Rational), str, str], ...},
    }

Key rules baked in:
- Keys are Wyckoff letters only (`a`, `b`, `c`, ...), not `4a` / `8c`.
- Multiplicities are the atom counts per letter in the unit cell — derived
  from `SpacegroupAnalyzer(struct).get_symmetry_dataset().wyckoffs`, which
  returns one letter per atom.
- Coordinates are the fractional coords of the FIRST atom for each letter,
  rendered as exact rationals with denominator <= 12 via
  `sympy.Rational(c).limit_denominator(12)`.
- If the symmetry dataset cannot be computed, returns empty dicts.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from typing import Any

try:
    from pymatgen.core import Structure
    from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
except ImportError:
    print("Error: pymatgen is not installed. Install with: pip install pymatgen", file=sys.stderr)
    raise

try:
    from sympy import Rational
except ImportError:
    print("Error: sympy is not installed. Install with: pip install sympy", file=sys.stderr)
    raise


def analyze_wyckoff_position_multiplicities_and_coordinates(
    filepath: str,
    denominator_limit: int = 12,
) -> dict[str, dict] | dict[str, Any]:
    """Return per-letter Wyckoff multiplicities and first-atom fractional coords.

    Args:
        filepath: Path to a CIF / POSCAR / any pymatgen-readable structure file.
        denominator_limit: Max denominator passed to `Rational.limit_denominator`.

    Returns:
        Dict with keys `wyckoff_multiplicity_dict` (letter -> int atom count)
        and `wyckoff_coordinates_dict` (letter -> [str, str, str] of rationals).
        Both empty if spglib cannot produce a symmetry dataset.
    """
    structure = Structure.from_file(filepath)
    dataset = SpacegroupAnalyzer(structure).get_symmetry_dataset()
    if dataset is None:
        return {"wyckoff_multiplicity_dict": {}, "wyckoff_coordinates_dict": {}}

    wyckoff_letters = dataset.wyckoffs  # one letter per atom in the structure

    multiplicity_dict = dict(sorted(Counter(wyckoff_letters).items()))

    sites_by_letter: dict[str, list] = defaultdict(list)
    for i, site in enumerate(structure):
        sites_by_letter[wyckoff_letters[i]].append(site)

    coordinates_dict: dict[str, list[str]] = {}
    for letter, sites in sorted(sites_by_letter.items()):
        coords = sites[0].frac_coords
        coordinates_dict[letter] = [
            str(Rational(c).limit_denominator(denominator_limit)) for c in coords
        ]

    return {
        "wyckoff_multiplicity_dict": multiplicity_dict,
        "wyckoff_coordinates_dict": coordinates_dict,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print Wyckoff multiplicities and first-atom fractional coords for a structure file."
    )
    parser.add_argument("structure_file", help="Path to CIF / POSCAR / pymatgen-readable file.")
    parser.add_argument(
        "--denominator-limit",
        type=int,
        default=12,
        help="Max denominator for rational coords (default: 12).",
    )
    args = parser.parse_args()

    result = analyze_wyckoff_position_multiplicities_and_coordinates(
        args.structure_file, denominator_limit=args.denominator_limit
    )
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
