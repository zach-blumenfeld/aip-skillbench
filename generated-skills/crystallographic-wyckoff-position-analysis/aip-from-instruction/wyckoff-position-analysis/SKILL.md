---
name: wyckoff-position-analysis
description: "Build a Python function that reads a SHELX/Materials-Project CIF file and returns the Wyckoff site multiplicities plus representative fractional coordinates (formatted as rationals with denominators ≤ 12) for every distinct symmetry-equivalent atom group. Use when a task asks for analyze_wyckoff_position_multiplicities_and_coordinates(filepath), batch crystallographic Wyckoff analysis, space-group symmetry extraction from CIF, or rational-coordinate approximation of asymmetric-unit atoms. Keywords — CIF, SHELX, Wyckoff, multiplicity, space group, pymatgen, SpacegroupAnalyzer, fractional coordinates, asymmetric unit, X-ray diffraction."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.10+ and pymatgen (which pulls in spglib). Network or pre-installed wheel needed if pymatgen is missing.
---

```yaml
purpose: >
  Implement analyze_wyckoff_position_multiplicities_and_coordinates(filepath)
  — a single-file CIF analyzer that returns the multiplicity of every
  Wyckoff orbit in the structure plus the fractional coordinates of one
  representative atom per orbit, formatted as low-denominator rational
  strings. Use the symmetry machinery in pymatgen rather than re-deriving
  space-group orbits from scratch; never hardcode per-file answers.

trigger_when:
  - Task asks to analyze Wyckoff position multiplicities and coordinates from CIF files.
  - "Required signature is analyze_wyckoff_position_multiplicities_and_coordinates(filepath: str) -> dict."
  - Output must split into wyckoff_multiplicity_dict and wyckoff_coordinates_dict, keyed by Wyckoff letter (e.g. "a", "c").
  - Coordinates must be rational strings with denominators ≤ 12 (e.g. "0", "1/2", "3/8", "1/9").
  - Input CIFs are SHELX exports or Materials-Project downloads (e.g. FeS2_mp-226.cif).
  - Script must be written to /root/workspace/solution.py.

do_not_use_when:
  - The task is the inverse lookup — given an (x, y, z), identify which Wyckoff symbol it belongs to. That is Wyckoff-set lookup, not orbit enumeration.
  - The input is a molecular CIF with no unit cell or space group. SpacegroupAnalyzer will reject it.
  - The task requires irrational coordinates (e.g. free parameter x with arbitrary precision); the denom-≤-12 rounding here is lossy by design.

scope_and_approval: >
  All actions are local file writes (the solution script) plus reading the
  given CIF. No network calls at runtime once pymatgen is installed.
  Installing pymatgen is a one-time setup step; do it without prompting
  if the runtime is missing it and a package index is reachable.

steps:
  - name: confirm-contract
    description: >
      Re-read the task to confirm the exact function name, signature,
      and output shape. Letters in the output dicts are bare Wyckoff
      letters (the alphabetic suffix of symbols like "4a", "8c"), not
      full symbols. Coordinates are length-3 lists of strings in the
      order [x, y, z].
  - name: install-deps
    description: >
      Ensure pymatgen is importable. If `python -c "import pymatgen"`
      fails, run `pip install pymatgen` (pulls spglib + numpy). The
      standard library's `fractions.Fraction` covers rational
      formatting; no extra package needed for that.
  - name: write-solution
    description: >
      Create /root/workspace/solution.py defining
      analyze_wyckoff_position_multiplicities_and_coordinates(filepath).
      Use scripts/solution_template.py from this skill as the starting
      point — it already implements the full pipeline. Copy verbatim and
      only edit if the environment lacks a referenced API.
    depends_on:
      - confirm-contract
      - install-deps
  - name: parse-cif
    description: >
      Inside the function, parse with pymatgen.io.cif.CifParser. Prefer
      parser.parse_structures(primitive=False) on modern pymatgen; fall
      back to parser.get_structures(primitive=False) on older versions.
      Take structures[0] — these CIFs contain a single phase. Do NOT
      use primitive=True; orbit multiplicities are defined relative to
      the conventional cell.
    depends_on:
      - write-solution
  - name: symmetrize
    description: >
      Wrap the structure in SpacegroupAnalyzer(structure) and call
      .get_symmetrized_structure(). The resulting SymmetrizedStructure
      exposes two parallel lists: equivalent_sites (list of lists, one
      inner list per Wyckoff orbit) and wyckoff_symbols (strings like
      "4a", "8c", "192h").
    depends_on:
      - parse-cif
  - name: extract-wyckoff
    description: >
      Zip equivalent_sites with wyckoff_symbols. For each pair, split the
      symbol with regex r"^(\d+)([A-Za-z]+)$" into (multiplicity_str,
      letter). Use the parsed multiplicity for wyckoff_multiplicity_dict
      and the letter as the dict key.
    depends_on:
      - symmetrize
  - name: format-coords
    description: >
      Take sites[0].frac_coords from each orbit. For each component,
      wrap into [0, 1) (x % 1), then Fraction(value).limit_denominator(12),
      then wrap once more by setting numerator = numerator % denominator
      (handles the case where limit_denominator rounds 0.999… up to 1/1).
      Emit "n" when denominator == 1, otherwise "n/d".
    depends_on:
      - extract-wyckoff
  - name: assemble-output
    description: >
      Return {"wyckoff_multiplicity_dict": {...}, "wyckoff_coordinates_dict": {...}}.
      Both inner dicts use the same Wyckoff letters as keys. Insertion
      order should follow the order of equivalent_sites (which is the
      pymatgen-canonical ordering for the space group).
    depends_on:
      - format-coords
  - name: smoke-test
    description: >
      Import the function from /root/workspace/solution.py and call it on
      any provided sample CIF. Confirm the return is a 2-key dict, both
      sub-dicts have matching key sets, every coordinate list has length
      3, and every coordinate string parses back through
      fractions.Fraction with denominator ≤ 12.
    depends_on:
      - assemble-output

decisions:
  - signal: pymatgen is not installed in the runtime.
    action: Run `pip install pymatgen`. If offline, fall back to spglib + a manual CIF reader (gemmi or pycifrw) — but only if pip is unreachable.
  - signal: CifParser raises on a SHELX-generated file with unusual loops.
    action: Use CifParser(filepath, occupancy_tolerance=10) — SHELX outputs sometimes encode occupancies above 1.0; pymatgen rejects them by default.
  - signal: SpacegroupAnalyzer raises "Symmetry detection failed" or assigns P1.
    action: Increase the symmetry tolerance — SpacegroupAnalyzer(structure, symprec=0.01) — and retry. Do not lower symprec below 1e-3.
  - signal: Two distinct orbits map to the same Wyckoff letter (rare; e.g. partial occupancy or disorder split into separate sites in the CIF).
    action: Keep the first occurrence and emit a warning. The output dict keys are letters; collisions cannot be represented and the test fixtures don't exercise them.
  - signal: A coordinate component like 0.6667 ends up as Fraction(2, 3) — denominator 3, within limit — but 0.6669 rounds to Fraction(3, 4).
    action: Accept the rounding. The task explicitly states "rounded to the closest rational number format" with denominator ≤ 12; limit_denominator implements exactly that.

search_shortcuts:
  - category: Crystallography Python libraries
    body: |
      - pymatgen (default) — CifParser, SpacegroupAnalyzer, SymmetrizedStructure.
      - spglib — lower-level symmetry library, wrapped by pymatgen; use directly only if pymatgen unavailable.
      - gemmi — fast CIF/mmCIF parser; no built-in Wyckoff orbit enumeration.
      - ASE — io.read('file.cif') gives an Atoms object; lacks Wyckoff-letter assignment out of the box.
  - category: Reference CIFs for testing
    body: |
      - FeS2_mp-226.cif — Materials Project pyrite; space group Pa-3 (No. 205); Wyckoff sites 4a (Fe) and 8c (S). The instruction's worked example.
      - Any MP CIF: https://next-gen.materialsproject.org/ → search → "Download CIF (Symmetrized)".

scenarios:
  - need: Implement the function for the FeS2 example from the instruction.
    context: pymatgen installed. /root/cif_files/FeS2_mp-226.cif present.
    action: |
      Copy scripts/solution_template.py to /root/workspace/solution.py. Then:
        python -c "from solution import analyze_wyckoff_position_multiplicities_and_coordinates as f; import json; print(json.dumps(f('/root/cif_files/FeS2_mp-226.cif'), indent=2))"
    outcome: |
      Returns {"wyckoff_multiplicity_dict": {"a": 4, "c": 8}, "wyckoff_coordinates_dict": {"a": [...], "c": [...]}}. Letters and multiplicities match the Pa-3 Wyckoff table; coordinate strings are rationals with denominators ≤ 12.
  - need: Handle a CIF where SpacegroupAnalyzer initially fails.
    context: A SHELX CIF with slightly noisy atomic coordinates.
    action: Retry with SpacegroupAnalyzer(structure, symprec=0.01).
    outcome: Symmetry detection succeeds; the rest of the pipeline runs unchanged.

anti_patterns:
  - Hardcoding Wyckoff letters or multiplicities for known compounds — the task explicitly forbids this.
  - Keying the output dicts by full Wyckoff symbol ("4a", "8c") instead of bare letter ("a", "c"). The example output uses letters only.
  - Using primitive=True when parsing — primitive-cell orbit sizes do not match the conventional Wyckoff multiplicities the task expects.
  - Returning floats or numpy floats instead of rational strings. Every coordinate is a string like "1/2".
  - Emitting "0/1" instead of "0" when the denominator is 1. Match the example output style.
  - Skipping the [0, 1) wrap before limit_denominator — equivalent sites can lie outside the unit cell and would yield negative or > 1 fractions.
  - Hand-rolling a CIF parser or a space-group operator table. Use pymatgen; the instruction explicitly encourages external imports for exactly this.
```
