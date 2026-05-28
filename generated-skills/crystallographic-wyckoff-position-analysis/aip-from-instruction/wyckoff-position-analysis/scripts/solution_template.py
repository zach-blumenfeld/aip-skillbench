"""Reference implementation for analyze_wyckoff_position_multiplicities_and_coordinates.

Copy or adapt this into /root/workspace/solution.py for the task. The function
parses a CIF, runs spacegroup analysis with pymatgen, groups sites into
Wyckoff orbits, and returns the orbit multiplicities along with the
fractional coordinates of the first atom in each orbit, formatted as
low-denominator rational strings (denominator <= 12).
"""

import re
from fractions import Fraction
from typing import Any

from pymatgen.io.cif import CifParser
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer


_WYCKOFF_RE = re.compile(r"^(\d+)([A-Za-z]+)$")


def _format_frac(x: float, max_denom: int = 12) -> str:
    """Wrap x into [0, 1) and return its closest rational with denominator <= max_denom."""
    wrapped = x - int(x // 1)  # equivalent to x % 1 but explicit
    frac = Fraction(wrapped).limit_denominator(max_denom)
    # limit_denominator may round up to 1/1; wrap that back to 0/1.
    if frac.denominator != 0:
        frac = Fraction(frac.numerator % frac.denominator, frac.denominator)
    if frac.denominator == 1:
        return str(frac.numerator)
    return f"{frac.numerator}/{frac.denominator}"


def analyze_wyckoff_position_multiplicities_and_coordinates(
    filepath: str,
) -> dict[str, dict] | dict[str, Any]:
    """Return Wyckoff multiplicities and representative coordinates for a CIF.

    Output shape:
        {
            "wyckoff_multiplicity_dict": {<letter>: <multiplicity>, ...},
            "wyckoff_coordinates_dict":   {<letter>: ["x", "y", "z"], ...},
        }
    where coordinates are strings of the form "n", "n/d", with d <= 12.
    """
    # Parse the CIF. parse_structures is the modern API; fall back to
    # get_structures for older pymatgen versions.
    parser = CifParser(filepath)
    try:
        structures = parser.parse_structures(primitive=False)
    except AttributeError:
        structures = parser.get_structures(primitive=False)
    structure = structures[0]

    sga = SpacegroupAnalyzer(structure)
    sym_struct = sga.get_symmetrized_structure()

    multiplicity_dict: dict[str, int] = {}
    coordinates_dict: dict[str, list[str]] = {}

    for sites, symbol in zip(sym_struct.equivalent_sites, sym_struct.wyckoff_symbols):
        match = _WYCKOFF_RE.match(symbol)
        if match:
            multiplicity = int(match.group(1))
            letter = match.group(2)
        else:
            # Defensive fallback: derive multiplicity from orbit size and
            # take any trailing alpha chars as the letter.
            multiplicity = len(sites)
            letter = "".join(ch for ch in symbol if ch.isalpha()) or symbol

        first = sites[0]
        coords = [_format_frac(c) for c in first.frac_coords]

        multiplicity_dict[letter] = multiplicity
        coordinates_dict[letter] = coords

    return {
        "wyckoff_multiplicity_dict": multiplicity_dict,
        "wyckoff_coordinates_dict": coordinates_dict,
    }


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print("Usage: solution.py <path/to/file.cif>", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(analyze_wyckoff_position_multiplicities_and_coordinates(sys.argv[1]), indent=2))
