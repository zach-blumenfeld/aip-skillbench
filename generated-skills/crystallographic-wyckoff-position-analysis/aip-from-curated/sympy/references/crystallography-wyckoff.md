# Crystallography: Wyckoff Position Analysis with SymPy + pymatgen

This reference covers the specific symbolic-math pattern needed to extract Wyckoff
position multiplicities and exact rational coordinates from a crystal structure
file (CIF). It pairs `pymatgen` (CIF I/O and space-group symmetry) with `sympy`
(`Rational.limit_denominator`) to deliver exact fraction results rather than
floating-point approximations.

Load this reference whenever the task involves:

- Reading CIF files produced by SHELX, X-ray diffraction, or the Materials Project.
- Determining Wyckoff letters (`a`, `b`, `c`, …) for atomic sites.
- Counting Wyckoff position multiplicities.
- Converting decimal fractional coordinates (e.g., `0.333…`) to exact rationals
  (e.g., `1/3`) with a bounded denominator.

## Background

A **Wyckoff position** is an equivalence class of atomic sites in a crystal that
share the same site symmetry under the space group. Each position is labeled by a
lowercase letter (`a`, `b`, `c`, …) inside a given space group. The
**multiplicity** of a Wyckoff position is the number of equivalent sites it
generates per conventional unit cell. **Fractional coordinates** describe an
atom's position as a fraction of the lattice vectors (typically rational numbers
like `0`, `1/2`, `1/3`, `1/4`, `1/6`, `1/8`).

Many crystallographic coordinates that *look* irrational are floating-point
artifacts of CIF storage — `0.6666666667` is really `2/3`, `0.875` is `7/8`.
The agent's job is to recover the exact fraction by approximating with a bounded
denominator using `sympy.Rational.limit_denominator(max_denominator)`.

## Required libraries

```python
from pymatgen.core import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from sympy import Rational
from collections import Counter, defaultdict
```

`pymatgen` handles CIF parsing and space-group analysis; `sympy` handles exact
rational arithmetic.

## Core pattern

### Step 1 — Load the structure

```python
structure = Structure.from_file(filepath)
```

`Structure.from_file` auto-detects format from the extension; for `.cif` it
parses lattice vectors, atomic sites, and site occupancies.

### Step 2 — Run symmetry analysis

```python
sga = SpacegroupAnalyzer(structure)
dataset = sga.get_symmetry_dataset()
```

`get_symmetry_dataset()` returns a spglib dataset (a dataclass-style object).
Access fields by **attribute**, not by dict key:

- `dataset.wyckoffs` — list of Wyckoff letters, one per atom in `structure.sites`,
  in the same order as `structure`.
- `dataset.equivalent_atoms` — array mapping each site to its representative
  equivalent atom index.
- `dataset.number` — space-group number.

Guard for `dataset is None` (rare: low-symmetry / unrecognized space group):

```python
if dataset is None:
    return {'wyckoff_multiplicity_dict': {}, 'wyckoff_coordinates_dict': {}}
```

### Step 3 — Multiplicity per Wyckoff letter

The multiplicity is simply the count of how many atoms in the unit cell share
each Wyckoff letter:

```python
wyckoff_letters = dataset.wyckoffs
multiplicity_dict = dict(sorted(Counter(wyckoff_letters).items()))
```

Sort by letter so output is deterministic.

### Step 4 — Coordinates of the representative atom for each letter

Pick the **first** site with each Wyckoff letter as the representative:

```python
wyckoff_sites = defaultdict(list)
for i, site in enumerate(structure):
    wyckoff_sites[wyckoff_letters[i]].append(site)

coordinates_dict = {}
for letter, sites in sorted(wyckoff_sites.items()):
    coords = sites[0].frac_coords           # numpy array of 3 floats
    exact = [str(Rational(c).limit_denominator(12)) for c in coords]
    coordinates_dict[letter] = exact
```

### Step 5 — Convert floats to exact fractions with bounded denominator

The bounded denominator is the crucial sympy step. `Rational(c)` converts the
Python/NumPy float to an exact `Rational` (which exposes the underlying binary
fraction — usually unwieldy). `.limit_denominator(N)` then finds the best
rational approximation whose denominator is ≤ N via Stern–Brocot search.

```python
from sympy import Rational
Rational(0.6666666667).limit_denominator(12)   # 2/3
Rational(0.5).limit_denominator(12)            # 1/2
Rational(0.125).limit_denominator(12)          # 1/8
Rational(0.090909).limit_denominator(12)       # 1/11
```

`str(rat)` yields canonical fraction form: `"1/2"`, `"2/3"`, `"0"`, `"1"`.

Choose the denominator cap based on what the problem allows. For typical
crystallographic coordinates a cap of `12` covers `1/2, 1/3, 1/4, 1/6, 1/8, 1/9, 1/12`
and rejects spurious 5-digit floats. The task-supplied instruction usually states
the cap explicitly ("constrain fractions to have denominators ≤ 12") — use that
value verbatim, do not invent your own.

## Output format

Return a single dict with two sub-dicts:

```python
{
    "wyckoff_multiplicity_dict": {"a": 4, "c": 8},
    "wyckoff_coordinates_dict": {
        "a": ["0", "1/2", "1/2"],
        "c": ["3/8", "1/9", "8/9"]
    }
}
```

Both sub-dicts must be keyed by Wyckoff letter and sorted alphabetically.
Coordinates are **lists of three strings**, not lists of `Rational` objects —
serialize with `str()`.

## Common pitfalls

1. **Treating the spglib dataset as a dict.** `dataset['wyckoffs']` raises;
   use `dataset.wyckoffs` (attribute access). Pymatgen ≥ 2024 returns a dataclass.
2. **Skipping `limit_denominator`.** `Rational(0.333333)` gives a
   16-digit denominator nightmare. Always cap.
3. **Picking the wrong denominator cap.** Use exactly the value the problem
   states. Higher caps may "find" spurious fractions; lower caps lose detail.
4. **Forgetting to sort the output dicts.** Tests compare exact dict equality;
   sort keys.
5. **Returning `Rational` objects instead of strings.** Coordinates must be
   strings (`"1/2"`), not SymPy `Rational` instances.
6. **Hardcoding answers.** The function must work on any CIF input; never
   pattern-match the file name.

## Verifying

After implementing, verify on a known case (FeS₂ pyrite, MP-226):

```python
result = analyze_wyckoff_position_multiplicities_and_coordinates("/root/cif_files/FeS2_mp-226.cif")
assert result == {
    "wyckoff_multiplicity_dict": {"a": 4, "c": 8},
    "wyckoff_coordinates_dict": {"a": ["0", "1/2", "1/2"], "c": ["3/8", "1/9", "8/9"]},
}
```
