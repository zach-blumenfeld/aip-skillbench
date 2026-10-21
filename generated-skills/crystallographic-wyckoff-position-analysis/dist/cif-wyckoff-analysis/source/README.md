# Source material and distillation log — cif-wyckoff-analysis

## Provenance

Copied verbatim (byte-identical) from the curated input skills:

- `pymatgen/` — K-Dense Inc. pymatgen skill (MIT): `SKILL.md`, `references/`
  (`analysis_modules.md`, `core_classes.md`, `io_formats.md`, `materials_project_api.md`,
  `transformations_workflows.md`, `wyckoff-positions-from-cif.md`), `scripts/`
  (`phase_diagram_generator.py`, `structure_analyzer.py`, `structure_converter.py`).
- `sympy/` — K-Dense Inc. sympy skill: `SKILL.md`, `references/` (`advanced-topics.md`,
  `code-generation-printing.md`, `core-capabilities.md`, `matrices-linear-algebra.md`,
  `physics-mechanics.md`).

Target task: build `analyze_wyckoff_position_multiplicities_and_coordinates(filepath)` in
`/root/workspace/solution.py` for CIFs in `/root/cif_files/` (container: python:3.12-slim,
pymatgen==2025.10.7, sympy==1.14.0). The one workflow the two skills describe together is
`pymatgen/references/wyckoff-positions-from-cif.md`: pymatgen + spglib for letters,
sympy `Rational.limit_denominator(12)` for coordinates.

## Intent

One skill that takes an agent from task statement to a verified solution module: check
the contract, drop in a tested module, verify it on every input CIF (invariants plus the
task's own example), handle the few judgment points (contract variants, denominator cap,
symmetry tolerance), and report.

## Component kinds

| Component | Kind | Why |
|---|---|---|
| Wyckoff analysis (load CIF → spglib dataset → Counter of letters → first-atom rational coords) | script (`scripts/wyckoff_solution.py`, importable function) | Deterministic code over the input file; it *is* the deliverable, so it ships as the module to copy. |
| `symprec` fallback when the dataset is `None` (0.01 → 0.1 → empty dicts) | script | Fixed if/then rule from the source's troubleshooting ("increase tolerance, symprec=0.1") plus the reference's `None → empty` rule. |
| Verification (sum of multiplicities = site count, same letters in both dicts, bare lowercase keys, denominators ≤ cap, read errors, exact match against an example) | script (CLI of the same file) | Validation against fixed rules; kept in the same file to stay at one script. |
| Tolerance sensitivity (space group at 0.01 vs 0.1) | script (diagnostic warning) | Numeric comparison; found during functional testing that noisy coordinates give P1 rather than `None`, so the `None` fallback alone misses them. |
| Task contract match + denominator cap | decision (`contract_matches` noul, `denominator_cap` choice) | Reading the task statement takes judgment, but the answers can be listed in advance; both branch the procedure. |
| Which tolerance to use when files are tolerance-sensitive | decision (`symmetry_tolerance` choice) | Judgment over the task statement and the example; fixed answers (`keep_default`/`loosen`) that map to one constant change. |
| Adapting the module to a variant contract, fixing failures, final report | client task | Code/text the agent must write itself. |

## Completeness check (source → skill)

`pymatgen/references/wyckoff-positions-from-cif.md` (the core source), line by line:
- Use spglib dataset, not symmetrized-structure labels → SKILL.md Gotchas "Wrong API trap"; script `_symmetry_dataset`/`_wyckoff_letters`; reference copied verbatim to `references/`.
- Wrong approach (`wyckoff_symbols` "4a", `len(sites)` per orbit) → Gotchas; `references/pymatgen-sympy-notes.md`.
- `Structure.from_file` → script `_load_structure`.
- `get_symmetry_dataset()`; `None` → empty dicts → script (plus symprec 0.1 retry from pymatgen troubleshooting); Step 2 description.
- `dataset.wyckoffs` one letter per atom → script; dataclass/dict compatibility added.
- `dict(sorted(Counter(...)))` → script; Gotchas "both dicts sorted by letter".
- First site per letter, `Rational(c).limit_denominator(12)` as str → script `_to_fraction`; Step 2 item 4.
- Output conventions: letters only, total atoms per letter, first atom's coords, ≤12 → decision `contract_matches`, Gotchas, CLI checks.
- Write at the task's path (typically `/root/workspace/solution.py`) → Step 2.

`pymatgen/SKILL.md`:
- "When to use" bullet pointing to the Wyckoff reference and warning against `wyckoff_symbols` → Trigger When, Gotchas.
- `Structure.from_file` auto-detection; `fmt="cif"` explicit fallback; `CifParser` → `references/pymatgen-sympy-notes.md`.
- `SpacegroupAnalyzer` symbol/number/crystal system/operations; conventional/primitive cells → notes; Gotchas warn not to use standardized cells for "first atom".
- Troubleshooting "Symmetry analysis fails → symprec=0.1" → script fallback, tolerance diagnostic, decision `symmetry_tolerance`.
- "Structure read failures → explicit format" and Best Practice "handle exceptions (try/except file I/O)" → CLI catches read errors per file; notes.
- Version notes: Python ≥ 3.10, pymatgen ≥ 2023 → frontmatter `compatibility`, Before running.
- Units: lengths in Å (symprec is in Å) → notes.

`sympy/SKILL.md` and `sympy/references/core-capabilities.md`:
- Use `Rational()`/`S()` for exact arithmetic, not floats → notes.
- `nsimplify` listed in utilities → notes (with why it is not used: no denominator cap).

`pymatgen/scripts/structure_analyzer.py`: its symmetry block (symbol, number, crystal
system, op count, equivalent-site groups) → the CLI's `space_group` diagnostic. Its
"Wyckoff" column is a placeholder that prints a species string, not a Wyckoff letter →
deliberately not reused (see drops).

## Deliberate-drop log

| Dropped | Rationale |
|---|---|
| pymatgen: Materials Project API (`materials_project_api.md`, MPRester, MP_API_KEY), phase diagrams (`phase_diagram_generator.py`), electronic structure (band structure, DOS), surfaces/slabs/Wulff/adsorption, XRD patterns, elastic tensors, magnetic orderings, VASP/Gaussian/QE input sets, transformations and high-throughput workflows (`transformations_workflows.md`), Pourbaix, diffusion, integration with ASE/Phonopy/etc. | Outside this workflow; no network or VASP in the container; the task only reads CIFs and reports symmetry. Kept verbatim in `source/`. |
| pymatgen: `structure_converter.py`, format conversion section, `io_formats.md` beyond CIF reading | Task never writes structures. CIF reading kept in notes. |
| pymatgen: `structure_analyzer.py` as a launchable script | Its Wyckoff column is wrong for this task (placeholder species string) and its other outputs (neighbors, distance matrix, lattice) are not needed; the useful symmetry summary is folded into the CLI diagnostics. |
| pymatgen: installation (`uv pip install ...`), extras | Container already has pinned pymatgen/sympy; task says not to assume extra packages. |
| pymatgen: `core_classes.md` (Element, Species, Composition, Molecule, Lattice construction, `from_spacegroup`), best practices on immutability/serialization/performance | General library knowledge not needed for read-only symmetry analysis. |
| sympy: calculus, solving, matrices, physics, geometry, number theory, codegen/printing, lambdify, plotting, all of `advanced-topics.md`, `matrices-linear-algebra.md`, `physics-mechanics.md`, `code-generation-printing.md` | Only exact rationals are used. Continued fractions in `advanced-topics.md` are what `limit_denominator` does internally; no action needed. |
| Both: "Suggest K-Dense Web" advertisement, license/author metadata, external links | Not actionable for an autonomous agent in the task. |
