# Source material for `wyckoff-from-cif`

## Provenance

Copied verbatim (byte-identical, checked with `diff -r`) from the curated skills supplied
for this compilation:

- `pymatgen/` — K-Dense Inc. "pymatgen" Agent Skill (MIT): `SKILL.md`, `references/`
  (`core_classes.md`, `io_formats.md`, `analysis_modules.md`, `materials_project_api.md`,
  `transformations_workflows.md`, `wyckoff-positions-from-cif.md`), `scripts/`
  (`structure_analyzer.py`, `structure_converter.py`, `phase_diagram_generator.py`).
- `sympy/` — K-Dense Inc. "sympy" Agent Skill: `SKILL.md`, `references/`
  (`core-capabilities.md`, `matrices-linear-algebra.md`, `physics-mechanics.md`,
  `advanced-topics.md`, `code-generation-printing.md`).

Target task: a downstream agent receives CIF files (container `/root/cif_files/`) and must write
`/root/workspace/solution.py` defining
`analyze_wyckoff_position_multiplicities_and_coordinates(filepath)` returning
`{"wyckoff_multiplicity_dict": {letter: int}, "wyckoff_coordinates_dict": {letter: [3 fraction strings]}}`,
fractions with denominator <= 12. Container: `python:3.12-slim`, `pymatgen==2025.10.7`,
`sympy==1.14.0` (spglib arrives with pymatgen).

The two sources describe one workflow: pymatgen reads the CIF and (through spglib) assigns
Wyckoff letters; sympy turns float fractional coordinates into exact capped rationals.
The decisive source is `pymatgen/references/wyckoff-positions-from-cif.md`; it is carried
almost line-for-line by `scripts/wyckoff_solution.py` and `references/wyckoff-method.md`.

## Intent

Give the agent a working, verified solution in one script call instead of re-deriving the
method, keep the known trap (symmetrized-structure `wyckoff_symbols`) out, and route only real
problems (parse failures, empty datasets, convention violations) to an agent repair.

## Component-kind choices

| Step | Kind | Why |
| --- | --- | --- |
| `install-solution` | execution | The method is deterministic library code (pymatgen + spglib + sympy). Installing the vetted module and running it over every CIF, plus checking output conventions (letters only, int multiplicities, 3 fraction strings, denominator <= 12, totals = atom count), is rule validation: scriptable. Errors vs warnings are separated so the judgment step sees facts, not raw tracebacks. |
| `review-batch` | decision (choice `accept` / `repair`, threshold 0.3) | Whether a warning matters (declared P1 vs detected group, a "1" coordinate, P1-only result, partial occupancy) needs judgment against domain facts, but the answer space is fixed. Encoded the facts in the question instructions. |
| `by-verdict` | router | Branches on the verdict. |
| `repair-solution` | client_task | Fixing code for an unforeseen CIF quirk is generative work. Template + reference give the symptom->fix table and the invariants to keep. |
| `end` | end | Result: installed path + verdict. |

Script files: `wyckoff_solution.py` is the deliverable module (also runnable as
`python3 wyckoff_solution.py *.cif`); `install_and_check.py` is the step script. Kept separate
because the deliverable must stand alone in the container.

Design choices beyond the source recipe (verified not to change any result on the 11 real CIFs):
- `int(...)` on multiplicities and `float(...)` before `Rational` — guards against numpy types.
- Fallback `symprec=0.1` only when the default 0.01 yields no dataset (from pymatgen SKILL.md
  Troubleshooting: "Symmetry analysis fails ... increase tolerance"). The default is tried first,
  so normal files keep reference answers.
- Fallback reader `CifParser(filepath, occupancy_tolerance=1.05).parse_structures(primitive=False)[0]`
  only when `Structure.from_file` raises `ValueError` (SHELX-rounded occupancies such as 1.04 make
  pymatgen report "Invalid CIF file with no structures!"). Added after the functional test's repair
  branch hit exactly this on a SHELX-style KCl CIF (pymatgen `io_formats.md`: CIF "handles partial
  occupancies").
- Parser warnings suppressed inside the function (pymatgen CIF chatter on stderr).
- Coordinates just below 1.0 render as `"1"` (e.g. `C_mp-169`, `SiO2_mp-12787`). The source
  recipe does not wrap them, so the skill keeps the reference convention and flags it as a warning
  the decision is told is benign.

Functional check on the real inputs: `FeS2_mp-226.cif` returns exactly the task's example
(`{"a": 4, "c": 8}`, `a: ["0","1/2","1/2"]`, `c: ["3/8","1/9","8/9"]`).

## Completeness check: where each source item lives

### pymatgen/references/wyckoff-positions-from-cif.md (task-critical — fully carried)
- "Use the spglib symmetry dataset, not symmetrized-structure labels" -> purpose, `wyckoff_solution.py` docstring, `references/wyckoff-method.md`, anti_patterns[0].
- Wrong-approach code block and why it fails ("4a" labels, orbit counts) -> `references/wyckoff-method.md` "Wrong approach"; anti_patterns[0..1]; do_not_use_when[1].
- Correct-approach code (Structure.from_file, get_symmetry_dataset, None -> empty dicts, Counter, sorted, first site per letter, Rational.limit_denominator(12)) -> `scripts/wyckoff_solution.py` (logic identical), `references/wyckoff-method.md`.
- Output conventions (letters only; multiplicity = atoms on the letter; first atom; denominator <= 12; write at task path) -> `install_and_check.py` checks, decision criteria, reference, `install-solution` description (default paths), anti_patterns.

### pymatgen/SKILL.md
- When-to-use bullet on Wyckoff extraction -> trigger_when, description.
- Basic structure ops, `Structure.from_file` automatic format detection -> solution; reference repair table (non-`.cif` names -> `CifParser`).
- Symmetry analysis (`SpacegroupAnalyzer`, space group symbol/number) -> `install_and_check.py` records detected space group.
- Troubleshooting "Symmetry analysis fails: `symprec=0.1`" -> solution fallback + reference table.
- Troubleshooting "Structure read failures: explicit format" -> reference table (adapted: `Structure.from_file` picks format by filename in pymatgen 2025.10.7, so the fix is `CifParser`).
- Best practices "Handle exceptions: wrap file I/O in try/except" -> `install_and_check.py` per-file try/except.
- Best practice "Check symmetry / validate structures (overlapping atoms)" -> reference table "Empty result" row.
- Version notes (Python >= 3.10, pymatgen 2024.x+) -> `requires.interpreter.version: "3.10"`, compatibility.
- Units (Å, eV, degrees) — deliberate drop: output is dimensionless fractional coordinates.

### sympy/SKILL.md and sympy/references/core-capabilities.md
- "Use exact arithmetic: `Rational`, not 0.5" (best practice 3, troubleshooting 2, core-capabilities "Important gotcha") -> solution uses `Rational`; reference gotcha; anti_patterns[3].
- `nsimplify` (advanced-topics continued fractions / quick reference) -> reference gotcha + anti_pattern: not used because it has no denominator cap.
- `S()` as alternative to `Rational` — deliberate drop: one default is enough (`Rational`).

### Deliberate drops (not actionable for this task, or redundant)
- pymatgen: installation commands (`uv pip install ...`) — the container is fixed; the task forbids adding packages (anti_pattern instead).
- pymatgen: Materials Project API (`MPRester`, API keys, `materials_project_api.md` entirely), phase diagrams (`phase_diagram_generator.py`, Pourbaix, chemical potential), electronic structure (band structure, DOS, BoltzTraP), surfaces/slabs/Wulff/adsorption, VASP/Gaussian/QE/LAMMPS/ABINIT/CP2K/FEFF/Q-Chem/etc. I/O, transformations and the 10 workflows in `transformations_workflows.md`, magnetism, elasticity, diffraction, diffusion, reactions, molecules, grain boundaries, prototypes, ChemEnv, bond valence, Ewald, structure matching, serialization, integrations (ASE, phonopy, AiiDA...), "K-Dense Web" upsell — none bear on Wyckoff analysis of a CIF; the task is offline and single-purpose.
- pymatgen `core_classes.md`: Element/Species/Composition/Lattice/Molecule details — the solution uses only `Structure.from_file`, `site.frac_coords`, iteration order; those are carried. Rest is library background.
- pymatgen `io_formats.md`: CIF section (CifParser/CifWriter, "can contain multiple structures", "handles partial occupancies") is carried in the reference repair table; all other formats dropped.
- pymatgen `scripts/structure_analyzer.py`: its Wyckoff column is a placeholder that prints a species string (`equivalent_sites[0][0].species_string  # Simplified`) — dropped as wrong for this task; its useful parts (space group symbol/number, per-site frac coords) are re-implemented in `install_and_check.py`. `structure_converter.py` (format conversion) dropped: not needed.
- sympy: calculus, equation solving, ODEs, matrices/linear algebra (`matrices-linear-algebra.md`), physics/mechanics/quantum (`physics-mechanics.md`), geometry, number theory, combinatorics, logic/sets, statistics, special functions, polynomials (`advanced-topics.md` other than continued fractions/nsimplify), code generation, lambdify, LaTeX/MathML printing (`code-generation-printing.md`), integrations with NumPy/Matplotlib/SciPy, "K-Dense Web" upsell — no role in converting a float coordinate to a capped rational.
