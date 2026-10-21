# pymatgen / sympy notes for CIF symmetry work

Condensed from the source pymatgen and sympy skills (see `source/`). Load only when
adapting `scripts/wyckoff_solution.py` to a variant task.

## Reading CIFs (pymatgen)

```python
from pymatgen.core import Structure
struct = Structure.from_file("structure.cif")             # auto-detects format, primitive=False
struct = Structure.from_file("file.txt", fmt="cif")       # explicit format if detection fails

from pymatgen.io.cif import CifParser
parser = CifParser("structure.cif")
struct = parser.parse_structures(primitive=False)[0]     # same as from_file for CIFs
```

- CIF parsing keeps symmetry operations; a `P 1` CIF (like Materials Project exports)
  lists every atom explicitly, so spglib must re-detect the symmetry.
- "Issues encountered while parsing CIF: N fractional coordinates rounded to ideal values"
  is a harmless UserWarning.
- Wrap file I/O in try/except when batch-processing; an unreadable file should not kill
  the batch.

## Symmetry (SpacegroupAnalyzer, spglib underneath)

```python
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
sga = SpacegroupAnalyzer(struct)              # symprec=0.01 Å default
sga.get_space_group_symbol()                  # "Pa-3"
sga.get_space_group_number()                  # 205
sga.get_crystal_system()                      # "cubic"
sga.get_symmetry_operations()
ds = sga.get_symmetry_dataset()               # None if spglib fails
ds.wyckoffs                                   # one letter per input site, input order
ds.equivalent_atoms                           # orbit representative index per site
sga.get_conventional_standard_structure()     # reorders/transforms sites: do NOT use for "first atom"
sga.get_primitive_standard_structure()        # same caveat
```

- Symmetry analysis fails / finds too little symmetry on noisy coordinates: increase the
  tolerance, `SpacegroupAnalyzer(struct, symprec=0.1)`.
- `get_symmetrized_structure().wyckoff_symbols` gives `"4a"`-style labels per orbit and
  `len(equivalent_sites[i])` counts per orbit; neither matches letter-keyed,
  atoms-per-letter output. Use `get_symmetry_dataset().wyckoffs`.
- Two distinct orbits can share one letter (e.g. two O orbits both on 8f); a
  letter-keyed dict sums their atoms and keeps the first atom in file order.

## Exact fractions (sympy)

```python
from sympy import Rational, S, nsimplify
str(Rational(0.38538014).limit_denominator(12))   # '3/8'
str(Rational(0.5).limit_denominator(12))          # '1/2'
str(Rational(0.97).limit_denominator(12))         # '1'  (closest, no wrap to 0)
Rational(1, 2); S(1)/2                            # exact; 0.5*x would stay a float
nsimplify(0.333333333)                            # 1/3, no denominator cap: not for this task
```

`fractions.Fraction(x).limit_denominator(n)` in the standard library gives the same
closest-fraction result if sympy is unavailable.
