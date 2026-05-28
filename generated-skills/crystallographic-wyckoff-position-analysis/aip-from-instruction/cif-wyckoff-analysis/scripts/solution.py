"""Wyckoff position multiplicity + first-atom coordinate extractor for CIF files.

Entry function:
    analyze_wyckoff_position_multiplicities_and_coordinates(filepath) -> dict

Returns a dict of the form:
    {
        "wyckoff_multiplicity_dict": {<letter>: <multiplicity>, ...},
        "wyckoff_coordinates_dict":   {<letter>: [<x>, <y>, <z>], ...},
    }

Coordinates are stringified rationals (e.g. "0", "1/2", "3/8") with
denominators constrained to <= 12, matching the task's example output.

Uses pymatgen for CIF parsing and space-group / Wyckoff analysis. The
SpacegroupAnalyzer.get_symmetrized_structure() groups sites in the
asymmetric unit by their crystallographic equivalence; each group carries
a Wyckoff symbol (e.g. "8c") whose numeric prefix is the multiplicity
and whose letter is the Wyckoff label.
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Any

from pymatgen.io.cif import CifParser
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

_LETTER_RE = re.compile(r"[A-Za-z]+")
_MAX_DENOM = 12


def _coord_to_fraction_string(value: float) -> str:
    """Round a fractional coordinate to its nearest rational with denominator <= 12.

    Negative or >=1 coordinates are folded into [0, 1) first so that the
    rational representation matches the conventional Wyckoff coordinate
    range used in crystallography tables.
    """
    folded = float(value) % 1.0
    frac = Fraction(folded).limit_denominator(_MAX_DENOM)
    # Fraction(0) prints as "0" (no denominator) — matches the example output.
    if frac.denominator == 1:
        return str(frac.numerator)
    return f"{frac.numerator}/{frac.denominator}"


def _parse_wyckoff_symbol(symbol: str) -> tuple[int, str]:
    """Split a Wyckoff symbol like '8c' into (multiplicity=8, letter='c')."""
    letter_match = _LETTER_RE.search(symbol)
    if not letter_match:
        raise ValueError(f"Unrecognized Wyckoff symbol: {symbol!r}")
    letter = letter_match.group(0)
    digits = symbol[: letter_match.start()]
    multiplicity = int(digits) if digits else len(symbol)
    return multiplicity, letter


def _load_structure(filepath: str):
    """Read a CIF file and return the first pymatgen Structure.

    Supports both modern (`parse_structures`) and legacy (`get_structures`)
    pymatgen APIs so the skill works across versions.
    """
    parser = CifParser(filepath)
    if hasattr(parser, "parse_structures"):
        structures = parser.parse_structures(primitive=False)
    else:
        structures = parser.get_structures(primitive=False)
    if not structures:
        raise ValueError(f"No structures parsed from CIF: {filepath}")
    return structures[0]


def analyze_wyckoff_position_multiplicities_and_coordinates(
    filepath: str,
) -> dict[str, Any]:
    structure = _load_structure(filepath)
    analyzer = SpacegroupAnalyzer(structure)
    symmetrized = analyzer.get_symmetrized_structure()

    multiplicity_dict: dict[str, int] = {}
    coordinates_dict: dict[str, list[str]] = {}

    # equivalent_sites: list[list[PeriodicSite]] — one bucket per symmetry-equivalent set.
    # wyckoff_symbols:  list[str]                — one symbol per bucket (e.g. "4a", "8c").
    for equivalent_group, symbol in zip(
        symmetrized.equivalent_sites, symmetrized.wyckoff_symbols
    ):
        multiplicity, letter = _parse_wyckoff_symbol(symbol)
        # First atom of this Wyckoff group — preserve the first occurrence
        # if the same letter ever appears more than once (rare but possible
        # when distinct species share a Wyckoff label).
        if letter in multiplicity_dict:
            continue
        first_site = equivalent_group[0]
        multiplicity_dict[letter] = multiplicity
        coordinates_dict[letter] = [
            _coord_to_fraction_string(c) for c in first_site.frac_coords
        ]

    return {
        "wyckoff_multiplicity_dict": multiplicity_dict,
        "wyckoff_coordinates_dict": coordinates_dict,
    }


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print("usage: solution.py <path-to-cif>", file=sys.stderr)
        sys.exit(2)
    result = analyze_wyckoff_position_multiplicities_and_coordinates(sys.argv[1])
    print(json.dumps(result, indent=2))
