---
name: cif-wyckoff-analysis
description: Build and verify a Python function that reads a CIF file (e.g. SHELX / Materials Project P1 exports) with pymatgen, detects symmetry with spglib, and returns Wyckoff letter multiplicities plus the first atom's fractional coordinates per letter as sympy rationals with a capped denominator (≤12). Use for batch Wyckoff-position / multiplicity / representative-coordinate analysis of crystal structures, e.g. writing /root/workspace/solution.py with analyze_wyckoff_position_multiplicities_and_coordinates.
compatibility: Python>=3.10; pip packages pymatgen (tested 2025.10.7, brings spglib) and sympy (tested 1.14.0). No network needed.
---

# CIF Wyckoff Analysis

## Trigger When

1. A task asks for `analyze_wyckoff_position_multiplicities_and_coordinates(filepath)` or
   any function returning `wyckoff_multiplicity_dict` / `wyckoff_coordinates_dict`.
2. A task asks for Wyckoff letters, multiplicities, or representative fractional
   coordinates of the sites in CIF files.
3. Broader: batch symmetry/space-group analysis of CIF crystal structures with
   pymatgen + spglib, where coordinates must be reported as simple rational fractions.

## Purpose

Encapsulates the full CIF → Wyckoff pipeline: load the structure in file order,
take per-site Wyckoff letters from spglib's symmetry dataset (not the symmetrized
structure's `"4a"` labels), count atoms per letter, and render the first atom's
coordinates as closest fractions with denominator ≤ 12. It ships a ready solution
module with a verification CLI, so the agent's work is checking the task contract,
installing the module, and verifying it against the real files.

## Before running

Check that `python3 --version` is ≥ 3.10 and that
`python3 -c "import pymatgen.core, sympy, spglib"` succeeds. Name every missing
package before continuing; the target container (python:3.12-slim + pymatgen +
sympy) already has them, so do not pip-install anything there.

Run skill commands from this skill folder (skill paths below, e.g. `scripts/wyckoff_solution.py`, are relative to it); task paths such as
`/root/cif_files/` and `/root/workspace/solution.py` come from the task statement.

## Procedure

- [ ] 1. Decision: check the task contract
- [ ] 2. Script: install the solution module
- [ ] 3. Script: run and verify on every input CIF
- [ ] 4. Decision (only if a `tolerance-sensitive` warning appeared), then client task:
  resolve any failure and report

### 1. Decision — task contract (`contract`)

Input: the task statement. Answer both in one pass.

```yaml
contract_matches:
  type: noul
  instructions: >-
    Does the task ask for exactly this contract - entry function
    analyze_wyckoff_position_multiplicities_and_coordinates(filepath), returning
    {"wyckoff_multiplicity_dict": {letter: atom count}, "wyckoff_coordinates_dict":
    {letter: [x, y, z] fraction strings of the first atom on that letter}}?
  criteria:
    true: Same function name, same two keys, letters-only keys (a, c), counts of atoms.
    false: >-
      Different function name, key names, "4a"-style keys, per-orbit counts,
      different coordinate format, or extra required output fields.
denominator_cap:
  type: choice
  instructions: What denominator limit does the task put on coordinate fractions?
  criteria:
    twelve: >-
      "denominators <= 12", or an example consistent with that (e.g. 3/8, 1/9, 8/9).
    other_number: An explicit different integer limit.
    unspecified: No limit stated and no example to infer it from.
```

Answering `true` when the contract actually differs is the costly mistake (the grader
would reject the output), so reconsider any close call that leans `true`. Branching:
- `contract_matches: true` and `twelve` → step 2 unchanged.
- `other_number` → use that integer N: in step 2 set `MAX_DENOMINATOR = N` in the copied
  file, and pass `--max-denominator N` in step 3.
- `unspecified` → keep 12 (the source convention) and say so in the report.
- `contract_matches: false` → step 2, then adapt the copied file's entry-function name /
  return shape to the task (client task); read
  [references/wyckoff-positions-from-cif.md](references/wyckoff-positions-from-cif.md)
  and [references/pymatgen-sympy-notes.md](references/pymatgen-sympy-notes.md) first.

### 2. Script — install the solution module

```bash
mkdir -p /root/workspace
cp scripts/wyckoff_solution.py /root/workspace/solution.py   # from the skill folder
```

The module is self-contained (imports pymatgen and sympy only) and defines
`analyze_wyckoff_position_multiplicities_and_coordinates(filepath: str) -> dict`.
What it does, so you can adapt it if needed:
1. `Structure.from_file(filepath)` — keeps the file's cell and site order.
2. `SpacegroupAnalyzer(structure).get_symmetry_dataset()` at `symprec=0.01`; if that
   returns `None`, retries at `symprec=0.1`; if still `None`, returns both dicts empty.
3. `dataset.wyckoffs` → one letter per site; multiplicity = `Counter` of letters, sorted.
4. Coordinates = `frac_coords` of the first site (file order) with each letter, each as
   `str(sympy.Rational(c).limit_denominator(12))`; keys sorted.

### 3. Script — run and verify

```bash
python3 /root/workspace/solution.py /root/cif_files/*.cif
```

Prints one JSON line per file: `result` (the function's return) and `diagnostics`
(`n_sites`, `space_group`, `symprec_used`, `space_group_at_symprec_0.1`, `problems`,
`warnings`). Exit 0 means every file passed: multiplicities sum to the site count,
both dicts share the same letters, keys are bare lowercase letters, every coordinate
is a fraction string within the cap. Error lines (`"error": ...`) mean the file could
not be read. `warnings` are non-fatal: `tolerance-sensitive` means symprec 0.01 and
0.1 detect different space groups (noisy coordinates); handle it in step 4.

If the task statement gives an example output for a file that exists, also check it
exactly (paste the example's dict as JSON, double quotes):

```bash
python3 /root/workspace/solution.py /root/cif_files/FeS2_mp-226.cif \
  --expect /root/cif_files/FeS2_mp-226.cif '{"wyckoff_multiplicity_dict": {"a": 4, "c": 8}, "wyckoff_coordinates_dict": {"a": ["0", "1/2", "1/2"], "c": ["3/8", "1/9", "8/9"]}}'
```

`"match": true` is required. Finally confirm the import path the grader will use:
`cd /root/workspace && python3 -c "from solution import analyze_wyckoff_position_multiplicities_and_coordinates as f; print(f('<one cif>'))"`.

### 4. Decision — tolerance (`tolerance`), then client task

Ask only if some file has a `tolerance-sensitive` warning; otherwise the answer is
`keep_default`. Input: the task statement plus the flagged diagnostics.

```yaml
symmetry_tolerance:
  type: choice
  instructions: Which spglib tolerance should the solution use for every file?
  criteria:
    keep_default: >-
      The task gives no tolerance, or its example output is reproduced at
      symprec=0.01 (the pymatgen default that expected outputs are normally made with).
    loosen: >-
      The task explicitly asks for idealized/higher symmetry of noisy experimental
      coordinates or names a tolerance >= 0.1, and no example contradicts it.
```

Switching tolerance changes letters and counts for every file, so a wrong `loosen` is
the costly mistake; reconsider any close call that leans `loosen`. On `loosen`, set
`SYMPREC_DEFAULT` in `/root/workspace/solution.py` to the task's tolerance (else 0.1),
rerun step 3 including the `--expect` check, and keep it only if that still matches.

Then resolve and report:
- `problems` non-empty or `match: false`: read the gotchas below and
  [references/wyckoff-positions-from-cif.md](references/wyckoff-positions-from-cif.md),
  fix `/root/workspace/solution.py`, rerun step 3 until it exits 0.
- `symprec_used: 0.1`, an empty result, or `keep_default` on a tolerance-sensitive file:
  report the file as low-confidence symmetry (noisy or disordered coordinates).
- Report: the solution path, the per-file space group and multiplicity dict, and any
  file flagged above. Never hardcode results per file name; the function must compute
  everything from the CIF it is given.

## Gotchas

- **Wrong API trap:** `get_symmetrized_structure().wyckoff_symbols` gives `"4a"`, `"8c"`
  per orbit, and `len(equivalent_sites[i])` counts one orbit. The task wants letters only
  (`a`, `c`) with the total atoms on that letter; two orbits on the same letter (e.g.
  CF4 F atoms on 8f twice → `f: 16`) are summed.
- **"First atom" = file order.** Do not call `get_conventional_standard_structure()`,
  `get_refined_structure()`, `get_primitive_standard_structure()`, or
  `Structure.from_file(..., primitive=True)`; they reorder/move sites and change the
  reported coordinates and counts.
- **Rounding is closest-fraction, not wrap:** `limit_denominator(12)` can yield `"1"`
  (e.g. 0.99990696 → `1` in C_mp-169) or `"0"`; keep them as-is, the expected outputs are produced the
  same way. Integers print without a denominator (`"0"`, `"1"`), fractions as `"3/8"`.
- Coordinates are strings, multiplicities are ints, both dicts sorted by letter.
- spglib ≥ 2.5 returns the dataset as an object (`dataset.wyckoffs`); older returns a
  dict (`dataset["wyckoffs"]`). The module handles both.
- The "fractional coordinates rounded to ideal values" CIF warning is harmless; the
  module silences it.
- Materials Project CIFs are written in `P 1` with every atom listed; the space group in
  the file header is not the real one, spglib re-detects it (e.g. Pa-3 for pyrite).
