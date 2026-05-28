---
name: pymatgen
description: "Materials science toolkit for crystal structures and molecules — read/write 100+ formats (CIF, POSCAR, XYZ), analyze symmetry and Wyckoff positions, build phase diagrams, parse band structures and DOS, generate slabs and adsorption sites, and query the Materials Project. Use when working with crystal structures, CIF/POSCAR files, space groups, Wyckoff letters/multiplicities, phase stability, electronic structure outputs (vasprun.xml), VASP/Gaussian/Quantum ESPRESSO inputs, or the Materials Project API."
license: MIT
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
  skill-author: K-Dense Inc.
compatibility: Requires Python 3.10+, pymatgen >= 2023.x, and sympy (for the rational-coord output of scripts/wyckoff_analyzer.py). Optional extras&#58; mp-api (Materials Project), pymatgen[analysis,vis]. Set MP_API_KEY env var to use Materials Project endpoints.
---

```yaml
purpose: >
  Drive pymatgen end-to-end for crystalline materials work&#58; load a
  structure from any of 100+ formats, analyze symmetry (space group,
  Wyckoff letters and multiplicities, point group), transform it
  (supercell, substitution, primitive reduction), generate derivatives
  (slabs, adsorbate sites, magnetic orderings), build phase diagrams and
  read electronic-structure outputs, write inputs for VASP / Gaussian /
  Quantum ESPRESSO, and query the Materials Project database. Units are
  pymatgen-native&#58; Å, eV, degrees, μB. The body wires each capability to
  the matching script or reference; the Wyckoff-from-CIF workflow is
  bundled as scripts/wyckoff_analyzer.py because the obvious approach
  (get_symmetrized_structure().wyckoff_symbols) returns symbols of the
  wrong shape and one entry per orbit instead of per atom.

trigger_when:
  - Reading, writing, or converting crystal-structure files (CIF, POSCAR / CONTCAR, XYZ, cssr, ...).
  - Computing or inspecting space group, point group, crystal system, or symmetry operations.
  - Extracting Wyckoff letters, multiplicities, or representative fractional coordinates from a CIF.
  - Building primitive / conventional / supercell variants of a structure.
  - Constructing a phase diagram or asking whether a composition is on the convex hull.
  - Parsing vasprun.xml for band structure, DOS, band gap, or final energy.
  - Generating slabs, Wulff shapes, or adsorbate sites for a Miller index.
  - Writing VASP / Gaussian / Quantum ESPRESSO inputs from a structure (MPRelaxSet, MPStaticSet, MPNonSCFSet, GaussianInput, PWInput).
  - Querying the Materials Project (`MPRester`) by formula, chemical system, material ID, or property filter.
  - Generating XRD patterns, elastic tensors, or magnetic-ordering enumerations.
  - User mentions pymatgen, mp-api, spglib, CIF, POSCAR, vasprun, Materials Project, Wyckoff, or space group.

do_not_use_when:
  - The system is a non-periodic small molecule and the question is about conformers, force fields, or RDKit-style cheminformatics — use RDKit / OpenBabel / ASE.
  - The user wants a converged DFT result (k-points, ENCUT, XC functional) without running a calculation. This skill writes inputs and parses outputs; it does not run VASP or QE.

scope_and_approval: >
  Read-only on input files. Scripts under `scripts/` write derived files
  to user-specified output paths only (converted structures, VASP input
  decks, phase-diagram plots). Materials Project queries require
  `MP_API_KEY` in the environment and make outbound HTTPS calls; no other
  network access is performed. Safe to run without prompting except for
  the Materials Project network step, which the agent should flag if
  policy requires it.

steps:
  - name: load-structure
    description: >
      Load the input into a pymatgen `Structure` (or `Molecule` for
      isolated systems). Prefer `Structure.from_file(path)` — pymatgen
      auto-detects CIF, POSCAR / CONTCAR, XYZ, cssr, json, and dozens of
      code-specific formats. If detection fails, pass `fmt="cif"` (or the
      relevant tag) explicitly. For structures built from scratch, use
      `Lattice.cubic` / `Lattice.from_parameters` plus the `Structure`
      constructor, or `Structure.from_spacegroup(symbol, lattice, species,
      coords)` when the symmetry is known. See
      `references/core_classes.md` for Structure / Lattice / Molecule
      property surfaces.
    inputs:
      - name: structure-source
        type: string
        description: Path to a structure file, or an inline lattice + species + coords spec.
    outputs:
      - name: structure
        type: object
        description: pymatgen `Structure` (periodic) or `Molecule` (isolated).
  - name: inspect-basics
    description: >
      Pull the no-cost properties straight off the Structure&#58;
      `composition.reduced_formula`, `composition.hill_formula`,
      `get_space_group_info()`, `density`, `volume`, lattice parameters
      (`lattice.a/b/c/alpha/beta/gamma`). Use this for the quick
      "what is this?" question before deciding whether deeper analysis
      is needed.
    depends_on: [load-structure]
    inputs:
      - name: structure
        type: object
    outputs:
      - name: basics
        type: object
        description: Reduced formula, space group, density, volume, lattice params.
  - name: analyze-symmetry-and-wyckoff
    description: >
      Two paths, picked by the question being asked.

      (a) For a general symmetry report — space group symbol/number,
      crystal system, point group, symmetry operations, equivalent-site
      groups — drive `pymatgen.symmetry.analyzer.SpacegroupAnalyzer`
      directly or invoke `scripts/structure_analyzer.py FILE --symmetry`.

      (b) For the per-letter Wyckoff workflow the task evaluates against
      — letters only (`a`, `c`, ...) keyed to atom counts and
      first-atom fractional coordinates as rationals with denominator
      <= 12 — use `scripts/wyckoff_analyzer.py` (function
      `analyze_wyckoff_position_multiplicities_and_coordinates(filepath)`).
      The script consumes `SpacegroupAnalyzer(struct).get_symmetry_dataset().wyckoffs`
      (which returns one letter per atom) and renders coords via
      `sympy.Rational(c).limit_denominator(12)`. DO NOT substitute
      `get_symmetrized_structure().wyckoff_symbols`&#58; it yields combined
      symbols like `4a` / `8c` and one entry per orbit, not per atom.

      If a symmetry call fails or returns `None`, raise `symprec`
      (`SpacegroupAnalyzer(struct, symprec=0.1)`); the helper returns
      empty dicts when spglib cannot produce a dataset at all. See
      `references/wyckoff-positions-from-cif.md` for the worked
      derivation.
    script: scripts/wyckoff_analyzer.py
    depends_on: [load-structure]
    inputs:
      - name: structure-or-path
        type: string
        description: Path to a CIF / structure file; the Wyckoff helper takes a path.
      - name: denominator-limit
        type: integer
        nullable: true
        description: Override the default rational denominator cap (default 12).
    outputs:
      - name: wyckoff-report
        type: object
        description: '{wyckoff_multiplicity_dict, wyckoff_coordinates_dict} keyed by letter only.'
  - name: analyze-coordination
    description: >
      Compute coordination numbers and neighbor environments with
      `pymatgen.analysis.local_env.CrystalNN`. Iterate sites and call
      `cnn.get_nn_info(struct, i)`; each neighbor record carries
      `site_index`, `weight`, and the contributing image. For a quick
      command-line summary use
      `scripts/structure_analyzer.py FILE --neighbors`. See
      `references/analysis_modules.md` for VoronoiNN, MinimumDistanceNN,
      and other neighbor-finding strategies.
    depends_on: [load-structure]
    inputs:
      - name: structure
        type: object
    outputs:
      - name: coordination-report
        type: object
        description: Per-site coordination numbers and neighbor lists.
  - name: convert-format
    description: >
      Convert a structure between file formats with
      `scripts/structure_converter.py INPUT OUTPUT` (single-file) or
      `scripts/structure_converter.py *.cif --output-dir DIR --format poscar`
      (batch). Programmatic path&#58; `struct.to(filename=...)`; pymatgen
      infers the format from the extension. Use this rather than
      hand-rolling a writer.
    script: scripts/structure_converter.py
    depends_on: [load-structure]
    inputs:
      - name: input-path
        type: string
      - name: output-path
        type: string
        description: Output file path (single) or output dir (batch with `--format`).
    outputs:
      - name: written-path
        type: string
  - name: transform-structure
    description: >
      Apply a `pymatgen.transformations.standard_transformations`
      pipeline&#58; `SupercellTransformation` for unit-cell expansion,
      `SubstitutionTransformation({"Fe": "Mn"})` for element swaps,
      `PrimitiveCellTransformation` to reduce to the primitive cell,
      `OrderDisorderedStructureTransformation` for partial occupancies.
      Chain transformations through a `TransformedStructure` to keep
      provenance. Reduce to the primitive cell before expensive analysis
      where the symmetry permits it. See
      `references/transformations_workflows.md` for the full catalog.
    depends_on: [load-structure]
    inputs:
      - name: structure
        type: object
      - name: transformations
        type: list[object]
        description: Ordered list of `AbstractTransformation` instances to apply.
    outputs:
      - name: transformed-structure
        type: object
  - name: query-materials-project
    description: >
      Use the `mp-api` package's `MPRester` inside a `with` block (always
      a context manager so the session closes). Search by formula,
      `chemsys`, or material id; filter on `energy_above_hull`,
      `band_gap`, etc. Common calls&#58; `mpr.get_structure_by_material_id`,
      `mpr.get_bandstructure_by_material_id`,
      `mpr.get_entries_in_chemsys` (input for phase diagrams),
      `mpr.materials.summary.search(...)`. Requires `MP_API_KEY` in the
      environment. See `references/materials_project_api.md`.
    inputs:
      - name: query
        type: object
        description: Material ID, formula, chemsys, or `summary.search` filter dict.
    outputs:
      - name: mp-records
        type: list[object]
        description: Structures, entries, band structures, or summary documents.
  - name: compute-phase-diagram
    description: >
      Build a phase diagram from a list of entries (typically from
      `mpr.get_entries_in_chemsys`). Use
      `scripts/phase_diagram_generator.py CHEMSYS --analyze "FORMULA"` for
      a single CLI invocation that fetches entries, builds the diagram,
      reports `energy_above_hull`, lists the decomposition products if
      unstable, and optionally writes a PDPlotter PNG. Programmatic path&#58;
      `PhaseDiagram(entries)` + `pd.get_e_above_hull(entry)` /
      `pd.get_decomposition(comp)`. See `references/analysis_modules.md`
      (Phase Diagrams section).
    script: scripts/phase_diagram_generator.py
    depends_on: [load-structure]
    inputs:
      - name: chemsys
        type: string
        description: Dash-separated element list, e.g. `Li-Fe-O`.
      - name: composition
        type: string
        nullable: true
        description: Optional target formula for `--analyze`.
    outputs:
      - name: pd-report
        type: object
        description: Hull energy, decomposition (if unstable), and optional plot path.
  - name: analyze-electronic-structure
    description: >
      Parse a VASP run with `pymatgen.io.vasp.Vasprun("vasprun.xml")`
      then drive `get_band_structure()` and `complete_dos`. Pull
      `bs.get_band_gap()` for gap energy + directness, `bs.is_metal()`,
      and `dos.get_element_dos()` for projected DOS. Plot with
      `BSPlotter` / `DosPlotter`. See `references/analysis_modules.md`
      (Electronic Structure section) and `references/io_formats.md`
      (VASP section).
    depends_on: [load-structure]
    inputs:
      - name: vasprun-path
        type: string
    outputs:
      - name: electronic-report
        type: object
        description: Band structure, DOS, band gap, metal/non-metal flag.
  - name: generate-surfaces-and-interfaces
    description: >
      Build slabs with `pymatgen.core.surface.SlabGenerator(struct,
      miller_index, min_slab_size, min_vacuum_size, center_slab=True)`
      and call `get_slabs()`. Combine with `AdsorbateSiteFinder` for
      on-top / bridge / hollow sites and with `WulffShape` for
      equilibrium morphology from per-facet surface energies. See
      `references/analysis_modules.md` (Surface and Interface section)
      and `references/transformations_workflows.md` (workflows 3 and 9)
      for a full slab → adsorbate → relax pipeline.
    depends_on: [load-structure]
    inputs:
      - name: bulk-structure
        type: object
      - name: miller-index
        type: list[integer]
      - name: surface-config
        type: object
        nullable: true
        description: min_slab_size, min_vacuum_size, center_slab, etc.
    outputs:
      - name: slabs
        type: list[object]
  - name: setup-calculation-inputs
    description: >
      Write input decks for downstream DFT codes. VASP&#58; `MPRelaxSet`,
      `MPStaticSet`, `MPNonSCFSet(struct, mode="line")` from
      `pymatgen.io.vasp.sets`; call `.write_input(directory)`. Customize
      with `user_incar_settings={"ENCUT": 600, ...}`. Gaussian&#58;
      `GaussianInput(mol, functional=..., basis_set=..., route_parameters=...)`.
      Quantum ESPRESSO&#58; `PWInput(struct, control={"calculation": "scf"})`.
      Prefer input sets over hand-rolling INCAR/KPOINTS — they encode the
      Materials Project's defaults and keep results comparable. See
      `references/io_formats.md` (Electronic Structure Code I/O) and
      `references/transformations_workflows.md`.
    depends_on: [load-structure]
    inputs:
      - name: structure-or-molecule
        type: object
      - name: target-code
        type: string
        description: One of `vasp-relax`, `vasp-static`, `vasp-bs`, `gaussian`, `qe`.
      - name: output-dir
        type: string
    outputs:
      - name: input-deck-path
        type: string
  - name: advanced-analysis
    description: >
      Specialty analyses that fan out from the loaded structure. Pick
      exactly one per invocation.
    depends_on: [load-structure]
    one_of:
      - 'xrd: `XRDCalculator().get_pattern(struct)` — 2θ peaks, hkl, intensities. Call `pattern.plot()` for a quick spectrum.'
      - 'elasticity: `ElasticTensor.from_voigt(matrix)` — bulk / shear / Young''s moduli via `.k_voigt`, `.g_voigt`, `.y_mod`.'
      - 'magnetic-ordering: `MagOrderingTransformation({"Fe": 5.0}).apply_transformation(struct, return_ranked_list=True)` — enumerate magnetic configurations and pick the lowest-energy one.'
      - 'diffusion / NEB / mechanical / dielectric: covered in `references/analysis_modules.md`.'
    inputs:
      - name: structure
        type: object
    outputs:
      - name: advanced-report
        type: object

modes:
  - name: cli
    body: >
      Use the bundled scripts as command-line entry points when the agent
      only needs a single answer&#58;
      `scripts/structure_converter.py INPUT OUTPUT`,
      `scripts/structure_analyzer.py FILE --symmetry --neighbors`,
      `scripts/phase_diagram_generator.py CHEMSYS --analyze "FORMULA"`,
      `scripts/wyckoff_analyzer.py FILE` (prints JSON).
  - name: library
    body: >
      Import pymatgen directly and chain calls. Preferred when the
      result feeds the rest of a Python program (e.g. writing
      `solution.py` for the task), when several analyses share a single
      loaded `Structure`, or when transformations need provenance via
      `TransformedStructure`.

search_shortcuts:
  - category: File formats and code I/O
    body: >
      `pymatgen.io.cif`, `pymatgen.io.vasp`, `pymatgen.io.gaussian`,
      `pymatgen.io.pwscf`, `pymatgen.io.lammps`, `pymatgen.io.xyz`,
      `pymatgen.io.cssr`. Convenience entry points&#58;
      `Structure.from_file`, `Structure.to`, `Molecule.from_file`.
  - category: Symmetry and Wyckoff
    body: >
      `SpacegroupAnalyzer.get_space_group_symbol()`,
      `.get_space_group_number()`, `.get_crystal_system()`,
      `.get_point_group_symbol()`, `.get_conventional_standard_structure()`,
      `.get_primitive_standard_structure()`, `.get_symmetry_dataset()`
      (use `.wyckoffs` for per-atom letters). See
      `references/wyckoff-positions-from-cif.md` for the per-letter
      multiplicity workflow.
  - category: Analysis modules
    body: >
      `pymatgen.analysis.local_env` (CrystalNN, VoronoiNN),
      `pymatgen.analysis.phase_diagram` (PhaseDiagram, PDPlotter,
      PourbaixDiagram), `pymatgen.analysis.diffraction.xrd`,
      `pymatgen.analysis.elasticity`, `pymatgen.analysis.adsorption`,
      `pymatgen.analysis.wulff`.
  - category: Materials Project
    body: >
      `mp_api.client.MPRester` — `get_structure_by_material_id`,
      `get_bandstructure_by_material_id`, `get_entries_in_chemsys`,
      `materials.summary.search(formula=..., chemsys=...,
      energy_above_hull=..., band_gap=...)`. Requires `MP_API_KEY` env
      var.
  - category: Transformations and input sets
    body: >
      `pymatgen.transformations.standard_transformations`
      (SupercellTransformation, SubstitutionTransformation,
      PrimitiveCellTransformation, OrderDisorderedStructureTransformation),
      `pymatgen.transformations.advanced_transformations`
      (MagOrderingTransformation, EnumerateStructureTransformation),
      `pymatgen.io.vasp.sets` (MPRelaxSet, MPStaticSet, MPNonSCFSet,
      MPHSEBSSet).

integrations:
  - partner: ASE (Atomic Simulation Environment)
    body: Round-trip via `AseAtomsAdaptor.get_atoms(struct)` / `.get_structure(atoms)` when a downstream pipeline (e.g. NEB, MD) speaks ASE.
  - partner: Phonopy
    body: Generate displaced supercells with pymatgen's `SupercellTransformation`, hand off to Phonopy for force-constant fitting.
  - partner: Atomate / Fireworks
    body: pymatgen input sets feed atomate workflows; the workflow framework handles submission, restart, and provenance.
  - partner: AiiDA
    body: Use `aiida-pymatgen` for `Structure ↔ StructureData` conversion and provenance tracking across runs.
  - partner: BoltzTraP
    body: Feed `vasprun.xml`-derived band structures into BoltzTraP for transport-property post-processing.

scenarios:
  - need: Compute per-letter Wyckoff multiplicities and first-atom fractional coordinates for a CIF the task delivers under `/root/cif_files/`.
    context: 'The task evaluates against `analyze_wyckoff_position_multiplicities_and_coordinates(filepath: str)` returning `{"wyckoff_multiplicity_dict": {letter: int}, "wyckoff_coordinates_dict": {letter: [str, str, str]}}` with letters only and rationals capped at denominator 12.'
    action: >
      Import and call `scripts/wyckoff_analyzer.py`'s
      `analyze_wyckoff_position_multiplicities_and_coordinates` from the
      task's `solution.py`. The helper consumes
      `SpacegroupAnalyzer(struct).get_symmetry_dataset().wyckoffs` (one
      letter per atom), Counter-aggregates to per-letter multiplicities,
      and renders the first atom's `frac_coords` through
      `sympy.Rational(c).limit_denominator(12)`. Write the resulting
      function at `/root/workspace/solution.py` as the task requires.
    outcome: 'A dict matching the task contract (`{"a": 4, "c": 8}`, `{"a": ["0", "1/2", "1/2"], "c": ["3/8", "1/9", "8/9"]}`-shaped) computed from the actual CIF, no hardcoded answers.'
  - need: Identify the space group and crystal system of a CIF before deciding on further analysis.
    action: >
      `Structure.from_file(path)` then
      `SpacegroupAnalyzer(struct).get_space_group_symbol()` /
      `.get_space_group_number()` / `.get_crystal_system()`. Or
      `scripts/structure_analyzer.py FILE --symmetry --export json`.
    outcome: Single-line space-group report keyed for use in downstream branching.
  - need: Check whether a candidate composition (e.g. `LiFeO2`) is on the convex hull of the `Li-Fe-O` chemsys.
    action: >
      Set `MP_API_KEY`, then
      `scripts/phase_diagram_generator.py Li-Fe-O --analyze "LiFeO2"` or
      programmatically&#58; fetch entries via
      `MPRester().get_entries_in_chemsys("Li-Fe-O")`, build
      `PhaseDiagram(entries)`, call `pd.get_e_above_hull(entry)` and
      `pd.get_decomposition(comp)` if the energy is positive.
    outcome: Hull energy in eV/atom plus, if unstable, the decomposition products.
  - need: Build a band-structure workflow for a known material.
    action: >
      Use the staged pipeline from
      `references/transformations_workflows.md` workflow 2&#58; MPRelaxSet
      → MPStaticSet (on the relaxed CONTCAR) → MPNonSCFSet (mode="line")
      → `Vasprun.get_band_structure()` → `bs.get_band_gap()`. Write each
      stage's inputs through `write_input(directory)`.
    outcome: A run-ready set of VASP input decks plus the post-processing call to extract the gap once the calculation completes.
  - need: Convert a directory of CIFs to POSCAR for batch DFT setup.
    action: '`scripts/structure_converter.py *.cif --output-dir ./poscar_files --format poscar`.'
    outcome: One POSCAR per input CIF, no hand-rolled writer.

anti_patterns:
  - 'Using `SpacegroupAnalyzer(struct).get_symmetrized_structure().wyckoff_symbols` for per-letter Wyckoff multiplicities. It returns combined symbols like `4a` / `8c` and one entry per orbit (not per atom); the task expects letters only and per-atom counts. Use `.get_symmetry_dataset().wyckoffs` via `scripts/wyckoff_analyzer.py` instead.'
  - 'Rendering Wyckoff coordinates with `str(float)` or `f"{x:.4f}"`. The task expects exact rationals with denominator <= 12; use `str(sympy.Rational(c).limit_denominator(12))`.'
  - 'Hardcoding the expected dict for a known CIF (e.g. the FeS2 example in the task). The script must derive it from the file every time.'
  - 'Calling `MPRester()` outside a `with` block. The session leaks; wrap every call in `with MPRester() as mpr: ...`.'
  - 'Hand-rolling INCAR/KPOINTS for a Materials-Project-style calculation when `MPRelaxSet` / `MPStaticSet` / `MPNonSCFSet` already encode the right defaults and keep your results comparable to MP entries.'
  - 'Running symmetry analysis on a structure with numerical noise and accepting `None`. Bump tolerance with `SpacegroupAnalyzer(struct, symprec=0.1)` and retry; `scripts/wyckoff_analyzer.py` only returns empty dicts when spglib truly cannot resolve a dataset.'
  - 'Iterating over Materials Project records one at a time when `summary.search(...)` accepts batched filters. Push filtering server-side via formula / chemsys / `energy_above_hull` / `band_gap` ranges.'
  - 'Skipping `Structure.from_file`''s automatic format detection in favor of a per-format reader. Default to `Structure.from_file(path)`; only pass `fmt=...` when detection fails.'
```
