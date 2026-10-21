# Wyckoff multiplicities and first-atom coordinates from CIF: method and repair guide

Load this when the batch check reported errors, or a warning you cannot explain, and you
must change `solution.py`.

## The method (keep it; it reproduces the task's reference answers)

```python
from collections import Counter, defaultdict
from sympy import Rational
from pymatgen.core import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

structure = Structure.from_file(filepath)          # full cell, CIF symmetry ops applied
dataset = SpacegroupAnalyzer(structure).get_symmetry_dataset()   # spglib, symprec=0.01
if dataset is None:
    return {"wyckoff_multiplicity_dict": {}, "wyckoff_coordinates_dict": {}}
letters = dataset.wyckoffs                          # one letter per atom, structure order
multiplicity = dict(sorted(Counter(letters).items()))
sites = defaultdict(list)
for i, site in enumerate(structure):
    sites[letters[i]].append(site)
coords = {k: [str(Rational(c).limit_denominator(12)) for c in v[0].frac_coords]
          for k, v in sorted(sites.items())}
```

## Output conventions

- Keys are Wyckoff **letters only** (`a`, `c`, `i`), never `4a` / `8c`.
- `wyckoff_multiplicity_dict[letter]` = total number of atoms in the unit cell carrying that
  letter (summed over all orbits/elements that share the letter), as a Python `int`.
- `wyckoff_coordinates_dict[letter]` = fractional coords of the **first** atom (in structure
  order) with that letter, as 3 strings of exact rationals with denominator <= 12:
  `str(sympy.Rational(x).limit_denominator(12))` -> `"0"`, `"1/2"`, `"3/8"`.
- Keys sorted alphabetically. Example (FeS2_mp-226, Pa-3):
  `{"wyckoff_multiplicity_dict": {"a": 4, "c": 8}, "wyckoff_coordinates_dict": {"a": ["0","1/2","1/2"], "c": ["3/8","1/9","8/9"]}}`

## Wrong approach (common mistake)

```python
symm = SpacegroupAnalyzer(struct).get_symmetrized_structure()
for i, sites in enumerate(symm.equivalent_sites):
    label = symm.wyckoff_symbols[i]  # "4a", "8c": multiplicity+letter, one per orbit
    multiplicity = len(sites)
```
Gives `4a`-style labels per orbit, and the per-letter totals come out wrong when two orbits
share a letter. Use `get_symmetry_dataset().wyckoffs`.

## Gotchas

- CIFs written by pymatgen / Materials Project declare `P 1` and list the whole cell; spglib
  then finds the real space group. Declared P1 vs detected higher group is normal.
- A coordinate just below 1.0 (e.g. 0.9999) rounds to `"1"`. The reference recipe keeps it;
  do not wrap it to `"0"` unless the task says so.
- Do not use floats like `0.5` for output and do not use `nsimplify` (no denominator cap);
  use `Rational(float(x)).limit_denominator(12)` (sympy exact arithmetic).
- `limit_denominator(12)` is an approximation by design ("approximate coordinates");
  0.385 -> 3/8, 0.1146 -> 1/9. Do not tighten it.
- Don't change `symprec` for files that already work: a looser tolerance can merge orbits and
  change letters. Use `symprec=0.1` only as a fallback when the default returns no dataset
  (pymatgen troubleshooting: "Symmetry analysis fails ... increase tolerance").

## Repair recipes (by symptom)

| Symptom | Fix |
| --- | --- |
| `Structure.from_file` fails: file does not end in `.cif` (format detected from the name) | `CifParser(path).parse_structures(primitive=False)[0]` (pymatgen.io.cif) reads it as CIF regardless of name. |
| `ValueError: Invalid CIF file with no structures!` — the real cause is in a pymatgen warning; re-run `CifParser(path).parse_structures(primitive=False)` with warnings shown. Most often "Species occupancies sum to more than 1" (SHELX rounding, e.g. 1.04) | The shipped solution already falls back to `CifParser(path, occupancy_tolerance=1.05)`; if a file still fails, raise the tolerance a little more (e.g. 1.1) only for that fallback, then `parse_structures(primitive=False)[0]`. Keep `primitive=False`: the primitive cell changes multiplicities. |
| Several data blocks in one file | Use the first structure from `CifParser(...).parse_structures(primitive=False)`; note it. |
| Partial occupancy / disordered sites | spglib sees each site once with its majority species; result is still per-site. Keep the per-site count; mention it. |
| Empty result (no dataset) | The shipped solution already retries `symprec=0.1`; if still empty, check the structure (overlapping atoms, wrong cell) and report the file. |
| Only P1 found for a structure whose CIF declares a higher group | Coordinates are noisy: retry that file with `symprec=0.05` then `0.1`; accept the first non-P1 dataset. |
| Any exception (e.g. `ZeroDivisionError`) on a file with no `_atom_site` loop or missing cell parameters (truncated upload) | Not a solution bug: there are no atoms to analyze. Leave the code alone and report the file as unanalyzable. |
| ImportError | The container has pymatgen 2025.10.7 and sympy 1.14.0 only; do not add other packages. |

After any change: keep the entry function name and signature
`analyze_wyckoff_position_multiplicities_and_coordinates(filepath: str)`, re-run it on every CIF,
and confirm the files that already worked give the same output as before.
