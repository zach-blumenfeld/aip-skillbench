# Source and provenance — wyckoff-positions-from-cif

## Provenance

Compiled from two curated Agent Skills, copied verbatim into this folder:

| Path | Origin | Author / license |
|------|--------|------------------|
| `pymatgen/` (SKILL.md, 6 references, 3 scripts) | curated `pymatgen` skill | K-Dense Inc., MIT |
| `sympy/` (SKILL.md, 5 references) | curated `sympy` skill | K-Dense Inc., SymPy BSD license |

The workflow these two skills describe together is the one in
`pymatgen/references/wyckoff-positions-from-cif.md`: read a CIF with pymatgen,
take one Wyckoff letter per atom from the spglib dataset, and express the first
atom's fractional coordinates as exact rationals with SymPy. Everything else in
both skills is general library documentation.

Target environment (from the task's Dockerfile): `python:3.12-slim`, `pymatgen==2025.10.7`,
`sympy==1.14.0` (spglib comes with pymatgen), CIFs in `/root/cif_files/`, work in
`/root/workspace/`. The input CIFs are Materials Project files expanded to P1
(`_symmetry_space_group_name_H-M 'P 1'`, every `_atom_site_symmetry_multiplicity`
is 1, oxidation-state species such as `Fe4+`, 913 B to 15.7 KB, up to 280 sites).
Every loader and default in the pack was run against all 11 of them.

## Intent

Give an agent the one rule that decides correctness for "Wyckoff positions from
CIF" tasks, as code rather than prose, and a validation loop that proves the
written solution matches it on every input file.

## Graph and step-kind choices

```
analyze-cifs (execution) → classify-convention (decision) → by-convention (router)
   standard → write-solution (execution) ─┐
   custom   → adapt-solution (client_task) ┴→ verify-solution (execution) → by-verification (router)
                                                 "true" → end
                                                 "false" → fix-solution (client_task) → verify-solution
```

| Step | Kind | Why this kind |
|------|------|---------------|
| analyze-cifs | execution | The Wyckoff computation is deterministic library code. The script runs the solution template itself (`assets/solution_template.py`), so the preview and the deliverable can't drift apart. It also adds diagnostics a script can compute: space group, site count, sum-of-multiplicities check, disorder, CIF-parser warnings, and symprec sensitivity (default vs 0.1). |
| classify-convention | decision (choice) | Whether the task text changes the output convention is a judgment over free text with a fixed answer space (standard / custom). Threshold 0.75: choosing wrong in either direction gives a wrong deliverable. |
| by-convention | router | Branches on the decision. |
| write-solution | execution | Standard case: render the template with the task's function name and write it. No reasoning needed, and rewriting by hand risks drift. |
| adapt-solution | client_task | Custom output shapes (e.g. `4a` keys, extra space-group field) need code generation. The template keeps the symmetry source, letter source, and rational formatting fixed, so only the parts the task changes are rewritten. |
| verify-solution | execution | Imports the written module from its real path and runs it on every CIF. Checks shape, JSON-serializability, key agreement, and multiplicity sum, and for the standard convention requires exact equality with the canonical analysis. |
| by-verification | router | Validation loop: pass → end, fail → fix. |
| fix-solution | client_task | Repairing code from listed problems is generation. After three failed attempts the template says to fall back to the canonical code. |
| end | end | The solution path, the verification result (per-file outputs), and the per-CIF analyses for the final answer. |

## Completeness check (source item → where it lives)

`pymatgen/references/wyckoff-positions-from-cif.md`:
- Wrong approach (`get_symmetrized_structure().wyckoff_symbols`, `len(sites)` counts orbits) → `anti_patterns[0]`; template docstring; `classify-convention` criteria.
- Correct approach code → `assets/solution_template.py`, line for line (adds only `str()`, `int()`, and `float()` casts so the return values are plain Python types; values are unchanged).
- `dataset is None` → empty dicts → template; anti-pattern "Raising when spglib finds no dataset"; analyze-cifs note.
- Keys are letters only, multiplicity = atoms per letter, coordinates of the first atom, `Rational(c).limit_denominator(12)` → template; decision criteria; anti-patterns on symbols, rounding, and representative choice.
- "Write the implementation at the path required by the task (typically /root/workspace/solution.py)" → `solution_path` / `function_name` start inputs; last anti-pattern.

`pymatgen/SKILL.md`:
- When-to-use bullet on Wyckoff extraction → `trigger_when`, `purpose`.
- `Structure.from_file` auto-detection → template. "Specify formats explicitly when automatic detection fails" (`fmt="cif"`) → `references/io_formats.md`, referenced from adapt/fix-solution for parse failures.
- `SpacegroupAnalyzer` symmetry API (symbol, number, crystal system, conventional/primitive) → `references/analysis_modules.md` (referenced for custom extra fields); analyze-cifs reports symbol and number.
- Troubleshooting "Symmetry analysis fails → increase tolerance (symprec=0.1)" → turned into a guard: analyze-cifs flags tolerance-sensitive files, and an anti-pattern forbids changing symprec. The convention uses the default, and on the real input C_mp-169.cif the space group changes (C2/m → R-3m), so following the generic tip would give a wrong answer.
- Best practices "Handle exceptions" and "Validate structures" → analyze-cifs catches errors per file and checks that multiplicities sum to the site count; verify-solution reports per-file exceptions.
- Core classes (Structure, PeriodicSite.frac_coords, Lattice, Composition) → `references/core_classes.md`.

`sympy/SKILL.md` and `sympy/references/core-capabilities.md`:
- "Use exact arithmetic: Rational / S, not floats" → template's Rational output; anti-pattern on floats/decimals; `references/sympy-core-capabilities.md` for custom rational formats.

`pymatgen/scripts/structure_analyzer.py`:
- Symmetry block (space group, point group, op count, equivalent site groups) → covered by analyze-cifs outputs.

## Deliberate-drop log

| Dropped from the procedure | Rationale |
|----------------------------|-----------|
| pymatgen install commands (`uv pip install pymatgen[...]`), Python/version notes | The container already has pymatgen 2025.10.7 and sympy 1.14.0. Installing extras is out of scope and may not be possible. |
| Materials Project API (MPRester, API keys), `materials_project_api.md`, `phase_diagram_generator.py` | Need network access and an API key. Not part of reading local CIFs. Kept in `source/pymatgen/`. |
| Phase diagrams, electronic structure (band structure, DOS), surfaces/slabs/Wulff/adsorption, VASP/Gaussian/QE input sets, diffraction, elasticity, magnetic ordering, high-throughput and band/surface workflows, `transformations_workflows.md` | Unrelated to Wyckoff analysis. Kept in `source/pymatgen/` for adjacent tasks; `do_not_use_when` points there. |
| `structure_converter.py` | Format conversion isn't part of the task. Kept in `source/`. |
| `structure_analyzer.py` site table "Wyckoff" column | Buggy: it prints `equivalent_sites[0][0].species_string`, not a Wyckoff symbol. Replaced by the template's correct logic. Coordination/distance-matrix options are unrelated. |
| Units and conventions (Å, eV, degrees), integration list (ASE, Phonopy, …), additional-resource links | Background. Fractional coordinates are unitless. |
| SymPy calculus, solving, matrices, physics/mechanics, code generation/printing, advanced topics (geometry, number theory, …), NumPy/SciPy/Matplotlib integration, troubleshooting | General SymPy documentation. Only `Rational` exact arithmetic is used. Full files kept in `source/sympy/`. |
| "Suggest using K-Dense Web" sections (both skills) | Vendor promotion. Has no use for an autonomous run. |
| Generic pymatgen best practices (IStructure immutability, as_dict serialization, MP API batching, workflow organization, performance) | Don't affect a single read-and-analyze pass. |

## Functional test record

- Standard path (`scratch/start.json`, all 11 real CIFs): analyze-cifs → classify-convention (standard) → write-solution → verify-solution (11/11, no problems) → end. Example: FeS2_mp-226 → `{'a': 4, 'c': 8}`, `{'a': ['0','1/2','1/2'], 'c': ['3/8','1/9','8/9']}`. The analysis takes about 0.4 s for all 11 files.
- Custom path ("4a"-keyed task): adapt-solution → verify-solution failed (numpy int64 left in the result on purpose) → fix-solution → verify-solution passed → end. All router branches were exercised.
- Edge inputs: a symmetrized (non-P1) Fm-3m CIF expands to 8 sites → `{'a': 4, 'b': 4}`. An unparseable CIF and a missing path are reported per file without aborting.
- Fresh-agent sessions (2):
  - Standard task: passed first time (11/11).
  - Custom task (`{'space_group', 'sites': {'4a': [...]}}`): passed.
  - Changes made from their feedback:
    - Step scripts no longer write `__pycache__` into the pack.
    - The anti-patterns now give the reason for "first atom in file order" and "keep `1`, don't wrap".
    - For custom conventions, verify-solution now returns each output next to the canonical analysis (`comparisons`) for review. Before, it only checked that the function ran.
    - The adapt template now says which space-group symbol call to use, how to handle a missing dataset, and when to count per letter versus per orbit (`dataset.equivalent_atoms`).
  - Known limit: on the standard path, verify-solution compares the written file against the same template that analyze-cifs runs. It proves the file was written, imports and runs. The convention itself rests on the curated `wyckoff-positions-from-cif.md`.
