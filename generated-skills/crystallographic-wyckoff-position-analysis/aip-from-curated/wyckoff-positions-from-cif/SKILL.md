---
name: wyckoff-positions-from-cif
description: Compute Wyckoff letters, per-letter multiplicities (atom counts), and representative exact-rational fractional coordinates from CIF crystal structures with pymatgen + spglib + sympy, and write/verify a Python solution function (e.g. /root/workspace/solution.py) returning wyckoff_multiplicity_dict and wyckoff_coordinates_dict. Use for Wyckoff position analysis, site symmetry, space-group site multiplicity, or "Wyckoff positions from CIF" tasks.
license: MIT
metadata:
  aip-version: "0.5a1"
  compiled-from: "pymatgen (K-Dense Inc.), sympy (K-Dense Inc.)"
---

# AIP runtime — format 0.5a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the JSON object a step receives. Each step declares its required keys as `inputs`; extra keys pass through.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the final state's shape.

## Execution

The state is one JSON object. It starts as the start step's `inputs` and flows along `inputs_to`; each step's output is merged over it, so keys accumulate and extra keys pass through untouched. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. You may change the state before any step runs; you have the final say at every step.

- **`execution`**: run `script` with one JSON object on stdin, `{"currentState": <state>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout; merge it over the state.
- **`decision`**: answer each question against the state. Each answer collapses to one value under its question name and is merged over the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the state, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the next step's `inputs`; merge them over the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. That state is the procedure's result.

```yaml
purpose: >
  Turn CIF files into Wyckoff multiplicity and coordinate dictionaries and a verified
  Python solution function. Carries the one non-obvious rule that decides correctness:
  take one Wyckoff letter per atom from the spglib dataset
  (SpacegroupAnalyzer(structure).get_symmetry_dataset().wyckoffs, default symprec),
  count atoms per letter, and report the first atom's fractional coordinates as
  sympy Rational(c).limit_denominator(12) strings — never the SymmetrizedStructure
  "4a"-style symbols or orbit counts. A script previews the canonical result on
  every input, a decision checks whether the task changes that convention, the
  solution is written from a canonical template (or adapted), and a script imports
  and runs it on every CIF until it verifies.

trigger_when:
  - A task asks for Wyckoff letters, Wyckoff multiplicities, or representative fractional coordinates of Wyckoff positions from CIF files.
  - A task asks to implement a function (typically in /root/workspace/solution.py) that takes a CIF path and returns wyckoff_multiplicity_dict and wyckoff_coordinates_dict.
  - Site-symmetry or space-group site analysis of crystal structures (CIF, P1-expanded Materials Project files such as SiO2_mp-6945.cif) with pymatgen and spglib.

do_not_use_when:
  - The task is general pymatgen work unrelated to Wyckoff sites (phase diagrams, band structures, DOS, surfaces, VASP input sets, Materials Project queries); see references/analysis_modules.md and source/pymatgen/ instead.
  - The task is pure symbolic mathematics with no crystal structure (use SymPy directly; source/sympy/ has the full guide).
  - The input is a molecule (XYZ, MOL) with no periodic lattice — Wyckoff positions do not apply.

steps:
  - name: analyze-cifs
    kind: execution
    description: Run the canonical Wyckoff analysis (the solution template itself) on every input CIF and collect space group, site count, multiplicities, coordinates, and diagnostics.
    inputs:
      - name: task_request
        type: string
        description: The task statement verbatim (function name, output path, output format).
      - name: cif_paths
        type: list[*]
        description: CIF files and/or directories of CIFs to analyze, e.g. ["/root/cif_files"]. Directories expand to their *.cif files.
      - name: solution_path
        type: string
        description: Where the solution module must be written, as the task states (typically /root/workspace/solution.py).
      - name: function_name
        type: string
        description: The function name the task requires, exactly as written in the task (e.g. analyze_wyckoff_position_multiplicities_and_coordinates).
    script: scripts/analyze_cifs.py
    assets:
      - assets/solution_template.py
    timeout: 300
    inputs_to: classify-convention

  - name: classify-convention
    kind: decision
    description: Decide whether the task wants the standard output convention or changes it.
    inputs:
      - name: task_request
        type: string
      - name: analysis_summary
        type: string
        description: One line per CIF from analyze-cifs (formula, space group, sites, multiplicities).
    questions:
      output_convention:
        type: choice
        instructions: >
          Does the task's requested output match the standard convention, or does it
          explicitly change it? Standard = a function taking a CIF path and returning a
          dict with wyckoff_multiplicity_dict ({letter: number of atoms with that
          letter}) and wyckoff_coordinates_dict ({letter: [x, y, z] of the first atom
          with that letter as exact fraction strings, denominator <= 12}), keys are
          letters only. Silence about a detail means standard. Only an explicit,
          contradicting requirement counts as custom.
        criteria:
          standard: The task asks for these two dicts (or does not specify more), letters-only keys, atom-count multiplicities, first-atom rational coordinates.
          custom: The task explicitly requires something different — "4a"-style keys, orbit counts, a different denominator or float coordinates, extra or renamed keys, a different return shape or argument.
    thresholds:
      output_convention: 0.75
    inputs_to: by-convention

  - name: by-convention
    kind: router
    description: Standard tasks get the canonical template written verbatim; custom ones get an adapted module.
    branch_on: output_convention
    branches:
      standard: write-solution
      custom: adapt-solution

  - name: write-solution
    kind: execution
    description: Render assets/solution_template.py with function_name and write it to solution_path.
    inputs:
      - name: solution_path
        type: string
      - name: function_name
        type: string
    script: scripts/write_solution.py
    assets:
      - assets/solution_template.py
    inputs_to: verify-solution

  - name: adapt-solution
    kind: client_task
    description: Write a solution module that keeps the canonical symmetry logic but follows the task's custom output convention.
    inputs:
      - name: task_request
        type: string
      - name: analysis_summary
        type: string
      - name: solution_path
        type: string
      - name: function_name
        type: string
    template: assets/adapt_solution.md
    assets:
      - assets/solution_template.py
    references:
      - path: references/wyckoff-positions-from-cif.md
        description: The canonical wrong-vs-right Wyckoff code and output conventions. Load before changing any part of the convention.
      - path: references/sympy-core-capabilities.md
        description: SymPy exact arithmetic (Rational, S, nsimplify). Load if the task asks for a different rational/float coordinate format.
      - path: references/analysis_modules.md
        description: pymatgen SpacegroupAnalyzer API (space group symbol/number, crystal system, symmetrized structure, conventional/primitive cells). Load if the task asks for extra symmetry fields.
      - path: references/io_formats.md
        description: pymatgen CIF reading/writing (CifParser, Structure.from_file, explicit fmt="cif"). Load if a CIF fails to parse or has partial occupancies.
      - path: references/core_classes.md
        description: Structure, PeriodicSite (frac_coords), Lattice, Composition. Load if the task asks for per-site species or coordinates beyond the first atom.
    inputs_to: verify-solution

  - name: verify-solution
    kind: execution
    description: Import the written solution, run the function on every CIF, and check serializability plus (standard) exact agreement with the canonical analysis or (custom) return outputs beside the canonical analysis for review.
    inputs:
      - name: solution_path
        type: string
      - name: function_name
        type: string
      - name: output_convention
        type: string
      - name: cif_files
        type: list[*]
        description: Resolved CIF paths from analyze-cifs.
      - name: analyses
        type: list[*]
        description: Canonical per-file analysis from analyze-cifs.
    script: scripts/verify_solution.py
    timeout: 300
    inputs_to: by-verification

  - name: by-verification
    kind: router
    description: Finish when the solution verifies; otherwise fix it and verify again.
    branch_on: verification_passed
    branches:
      "true": end
      "false": fix-solution

  - name: fix-solution
    kind: client_task
    description: Repair the solution file using the verification problems, then re-verify.
    inputs:
      - name: solution_path
        type: string
      - name: function_name
        type: string
      - name: output_convention
        type: string
      - name: task_request
        type: string
      - name: verification
        type: object
    template: assets/fix_solution.md
    assets:
      - assets/solution_template.py
    references:
      - path: references/wyckoff-positions-from-cif.md
        description: The canonical wrong-vs-right Wyckoff code. Load when a problem says the output differs from the canonical analysis.
      - path: references/io_formats.md
        description: pymatgen CIF parsing options. Load when the solution raises while reading a CIF.
    inputs_to: verify-solution

  - name: end
    kind: end
    description: A verified solution module plus the per-CIF Wyckoff results. For a custom convention, first review verification.comparisons against the task's format (go back to fix-solution if any output is wrong). Report the solution path and results (and any analyze-cifs notes) in the final answer.
    inputs:
      - name: solution_path
        type: string
      - name: function_name
        type: string
      - name: verification_passed
        type: boolean
      - name: verification
        type: object
        description: Per-file outputs of the written function and any problems (none when passed).
      - name: analyses
        type: list[*]

anti_patterns:
  - Using SpacegroupAnalyzer(...).get_symmetrized_structure().wyckoff_symbols — it yields "4a"-style labels per orbit and len(equivalent_sites) counts orbits per group, so letters-only keys and atom-count multiplicities both come out wrong.
  - Reporting the multiplicity printed in the CIF (_atom_site_symmetry_multiplicity); the inputs are P1-expanded Materials Project files where it is always 1. Multiplicity is the number of atoms carrying the letter in the full cell.
  - Changing symprec (e.g. 0.1) or symmetrizing/refining/standardizing the cell first. Letters and coordinates must come from the structure exactly as read with default symprec; C_mp-169 is C2/m at default but R-3m at 0.1.
  - Taking coordinates from the conventional/primitive standard cell, from dataset.std_positions, or from a "nicest" representative; the representative is the first atom in file order with that letter, because expected answers are generated by exactly that rule on the file as given.
  - Wrapping or rewriting rounded coordinates (e.g. "1" → "0", floats, decimals, or limit_denominator other than 12); use str(Rational(c).limit_denominator(12)) as-is — the reference convention does not post-process, so any "cleanup" diverges from it (C_mp-169 and SiO2_mp-12787 legitimately yield "1").
  - Returning "4a"-style keys, numpy ints/strings, or unsorted dicts; keys are plain letter strings, values plain ints and lists of strings, sorted by letter.
  - "Raising when spglib finds no dataset; return {\"wyckoff_multiplicity_dict\": {}, \"wyckoff_coordinates_dict\": {}}."
  - Hardcoding answers for the provided CIFs or depending on packages beyond pymatgen, sympy, and the standard library (the container has only pymatgen 2025.10.7 and sympy 1.14.0 on python 3.12).
  - Writing the function name or output path differently from the task statement.
```
