# Adapt the Wyckoff solution to the task's custom output convention

The task asks for something other than the standard convention (letters-only keys,
multiplicity = atoms per letter, first-atom coordinates as `limit_denominator(12)`
strings, two dicts `wyckoff_multiplicity_dict` / `wyckoff_coordinates_dict`).

Task request:

{task_request}

Canonical analysis of the inputs (standard convention, for comparison):

{analysis_summary}

Canonical solution (the `__FUNCTION_NAME__` placeholder is the function name):

```python
{assets[solution_template]}
```

Do this:

1. List exactly which parts of the convention the task changes (labels such as `4a`,
   orbit counts instead of atom counts, a different denominator or float output,
   extra keys such as space group, a different return shape, a different input
   argument). Everything the task does not change stays as in the canonical code.
2. Write the adapted module to `{solution_path}` with a function named
   `{function_name}`. Keep `SpacegroupAnalyzer(structure).get_symmetry_dataset()`
   at default `symprec` as the symmetry source unless the task names a tolerance;
   keep `dataset.wyckoffs` (one letter per atom) as the letter source; for
   `4a`-style labels use `f"{{multiplicity}}{{letter}}"` where multiplicity counts
   atoms. Use only pymatgen, sympy, and the standard library.
   - Space group symbol: `SpacegroupAnalyzer(structure).get_space_group_symbol()`
     (same as `dataset.international`, e.g. `P3_121`, `Pa-3`); number via
     `get_space_group_number()`.
   - Per-letter vs per-orbit: several orbits can share a letter (Al2O3_mp-7048 has
     20 atoms on `i`, i.e. five 4i orbits). If the task counts atoms on a position
     or letter, aggregate per letter (canonical). Only if it asks for the
     crystallographic site multiplicity / one entry per orbit, group atoms by
     `dataset.equivalent_atoms` and use each orbit's size and first atom.
   - When `get_symmetry_dataset()` returns None, return the empty form of the
     requested structure; do not raise.
3. Return `{{"solution_path": "<absolute path written>", "solution_written": true}}`.
