---
name: cif-wyckoff-analysis
description: Build a Python function that reads a SHELX/Materials-Project CIF file and returns per-Wyckoff-position multiplicities and the first atom's fractional coordinates (rounded to rationals with denominator <= 12). Use when the user asks to analyze crystallographic Wyckoff positions, batch-process CIF files for symmetry-equivalent site data, install a `analyze_wyckoff_position_multiplicities_and_coordinates(filepath)` solution at `/root/workspace/solution.py`, or otherwise extract Wyckoff multiplicity and approximate-rational coordinates from CIF input.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.10+ with pymatgen installed (pip install pymatgen). Write target `/root/workspace/solution.py` must be writable.
---

```yaml
purpose: >
  Produce a batch-ready Python function
  `analyze_wyckoff_position_multiplicities_and_coordinates(filepath)` that
  parses a CIF file, derives the Wyckoff-orbit multiplicities of each
  occupied position, and reports the first orbit member's fractional
  coordinates as rationals with denominator <= 12. The function is
  installed at `/root/workspace/solution.py` so an external grader can
  import and call it.

trigger_when:
  - The user provides a CIF file (or batch of them) and asks for Wyckoff multiplicities and/or per-position coordinates.
  - The user asks to write a function named `analyze_wyckoff_position_multiplicities_and_coordinates` or to populate `/root/workspace/solution.py` for a crystallography task.
  - The task hands you SHELX-derived or Materials Project CIF files and expects the two-key dict output containing `wyckoff_multiplicity_dict` and `wyckoff_coordinates_dict`.
  - Coordinates must be rounded to the nearest rational with a small denominator cap (<= 12 in this task).

do_not_use_when:
  - The user wants a *primitive-cell* analysis or a non-standard space-group setting — this skill assumes the conventional cell that pymatgen's `SpacegroupAnalyzer` produces.
  - The CIF carries partial occupancies or disorder that requires per-species Wyckoff splitting beyond the first-atom-per-letter convention.
  - The user wants raw decimal coordinates rather than the denominator-<=-12 rational form.

scope_and_approval: >
  Writes one file at `/root/workspace/solution.py` (overwriting any
  prior contents). Reads CIF inputs only. No network calls beyond pip
  install of pymatgen if it is missing. Confirm before overwriting a
  pre-existing solution that the user may have edited.

steps:
  - name: confirm-environment
    description: Verify Python 3.10+ and pymatgen are available; install pymatgen if missing. Confirm `/root/workspace/` exists and is writable.
    outputs:
      - name: env-ready
        type: boolean
        description: True once Python and pymatgen import successfully.

  - name: install-solution
    description: Copy `scripts/solution.py` from this skill to `/root/workspace/solution.py`. This is the canonical reference implementation — do not edit it inline unless a step below explicitly says so. See `references/pymatgen-wyckoff-cheatsheet.md` for the underlying API rationale.
    script: scripts/solution.py
    inputs:
      - name: env-ready
        type: boolean
    outputs:
      - name: solution-path
        type: string
        description: Absolute path of the installed solution file, expected to equal `/root/workspace/solution.py`.

  - name: smoke-test
    description: Import the installed solution and run it against one of the available CIF files (e.g. an `FeS2_mp-*.cif` or `SiO2_mp-*.cif` from the task environment). Confirm the return value is a dict with both `wyckoff_multiplicity_dict` and `wyckoff_coordinates_dict` keys, each value is a dict keyed by single-letter Wyckoff labels, multiplicities are positive integers, and every coordinate string parses as a `fractions.Fraction` with denominator <= 12.
    inputs:
      - name: solution-path
        type: string
    outputs:
      - name: smoke-result
        type: object
        description: The dict returned by the function on the chosen sample CIF.

  - name: handle-symprec-fallback
    description: If `smoke-test` reports a missing or trivial space group (P1) on a CIF the user believes is symmetric, re-run with a looser tolerance by editing the `SpacegroupAnalyzer(structure)` call in `/root/workspace/solution.py` to `SpacegroupAnalyzer(structure, symprec=0.1)`. Re-run the smoke test. Tighten back to the default if the user's data is clean.
    inputs:
      - name: smoke-result
        type: object
    outputs:
      - name: final-solution-status
        type: string
        description: One of `default-symprec-ok` or `loosened-symprec-applied`.

scenarios:
  - need: Grader runs `analyze_wyckoff_position_multiplicities_and_coordinates("/root/cif_files/FeS2_mp-226.cif")` and expects the documented dict shape.
    context: FeS2 pyrite is cubic (space group Pa-3, #205). Fe sits at Wyckoff position 4a; S sits at Wyckoff position 8c with one free positional parameter near 0.385.
    action: Install `scripts/solution.py` verbatim. The script parses the CIF with `CifParser`, symmetrizes via `SpacegroupAnalyzer`, walks `equivalent_sites` / `wyckoff_symbols`, and rounds each `frac_coords` entry through `Fraction(...).limit_denominator(12)`.
    outcome: >-
      Returns a dict whose `wyckoff_multiplicity_dict` is `{"a": 4, "c": 8}`
      and whose `wyckoff_coordinates_dict` carries the matching `"a"` and
      `"c"` coordinate triples — all rational strings with denominators
      <= 12. The exact rational values come from the data, not from
      hardcoded constants.

  - need: CIF lists negative or > 1 fractional coordinates produced by a symmetry operation (e.g. `-0.0001`).
    context: Symmetry operations occasionally emit coordinates just outside [0, 1) due to floating-point arithmetic. Naively passing these to `Fraction.limit_denominator` would produce visually wrong strings like `"-1/10000"`.
    action: The script folds every coordinate with `value % 1.0` before rationalizing, so `-1e-17` becomes `"0"` and `1.0000001` becomes `"0"`.
    outcome: Output strings stay in the conventional [0, 1) Wyckoff range.

  - need: Two distinct species share the same Wyckoff letter at different free-parameter values.
    context: The Wyckoff *letter* alone is not a unique key for a site in a structure — multiple orbits can carry the same label when the position has free parameters and is occupied more than once.
    action: >-
      The script preserves the first occurrence per letter — it skips
      subsequent symbols whose letter is already in the output dict — so
      the dict shape matches the task's contract.
    outcome: One coordinate triple per letter; no silent overwrites.

anti_patterns:
  - Hardcoding the worked example's literal output (the `"a"`/`"c"` rational triples shown in the instruction) instead of computing it from the CIF — the task explicitly forbids this and the grader runs on multiple CIFs.
  - Calling `CifParser(...).get_structures(primitive=True)` (or omitting the kwarg in old pymatgen, which defaults to True) — Wyckoff symbols are defined against the conventional cell.
  - Reading the space-group symbol from `SpacegroupAnalyzer.get_space_group_symbol()` and trying to recompute Wyckoff data from a lookup table — pymatgen's symmetrized structure already exposes the labelled orbits.
  - Using `round(c, 2)` or `f"{c:.3f}"` to "approximate" coordinates — the task asks for the closest rational, not decimal rounding. Use `Fraction(c).limit_denominator(12)`.
  - Printing zero as `"0/1"` — the example output shows `"0"`. `Fraction(0)` already renders as `"0"` via `str()`; do not reformat with `f"{n}/{d}"` unconditionally.
  - Letting symbol parsing assume a single-digit multiplicity (`symbol[0]`) — multiplicities like `16d` or `24h` exist in higher-symmetry groups. Strip all leading digits.
  - Writing the solution somewhere other than `/root/workspace/solution.py` — the grader imports from that exact path.
```
