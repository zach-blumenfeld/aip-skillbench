---
name: wyckoff-from-cif
description: Analyze Wyckoff positions of crystal structures in CIF files (SHELX / X-ray diffraction / Materials Project) with pymatgen + spglib + sympy. Writes a Python solution exposing analyze_wyckoff_position_multiplicities_and_coordinates(filepath) that returns, per Wyckoff letter, the multiplicity (atoms in the unit cell on that letter) and the fractional coordinates of the first atom as rationals with denominator <= 12, then batch-checks it on every CIF. Use for Wyckoff letters, site multiplicities, symmetry-equivalent positions, or rational coordinates from CIF files.
compatibility: Python >= 3.10 with pymatgen (spglib) and sympy; no network needed.
metadata:
  aip-version: "0.6a1"
  version: "1.0"
  compiled-from: "pymatgen, sympy skills (K-Dense Inc.)"
---

# AIP runtime — format 0.6a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the one JSON object a run carries. Each step declares the keys it reads as `inputs`; `execution` and `client_task` steps declare the keys they add as `outputs`, and a `decision` adds one key per question.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the procedure's result.

## Execution

The state starts as the start step's `inputs` and flows along `inputs_to`; each step adds its outputs to it. Every key is produced by exactly one step, so keys accumulate and nothing is overwritten. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. A step sees only those keys: give it its declared `inputs` and nothing else from the state. You have the final say at every step.

- **`execution`**: before the first one, check that this machine has everything `requires` names (the interpreter at its minimum version, the packages, the tools); if anything is missing, stop and name all of it. Run `script` from its folder, launched with the step's `command` when it has one and `python <script>` otherwise, with one JSON object on stdin, `{"state": <the step's inputs>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout holding exactly the step's `outputs`; add them to the state. A non-zero exit, or output missing a declared key, fails the step: stop there and report it rather than doing the step by hand.
- **`decision`**: answer each question from the step's inputs, and from the run so far only when the step sets `history: true`. Each answer collapses to one value under its question name and is added to the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the step's inputs, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the step's `outputs`; add them to the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. Those keys are the procedure's result.

```yaml
purpose: >
  Produce and verify a Python solution that, for one CIF file, returns Wyckoff letter ->
  multiplicity and Wyckoff letter -> fractional coordinates of the first atom on that letter
  (exact rationals, denominator <= 12). The method is fixed by the source skill: read the full
  cell with pymatgen Structure.from_file, take spglib's per-atom letters from
  SpacegroupAnalyzer(structure).get_symmetry_dataset().wyckoffs (default symprec 0.01), count
  atoms per letter, and round the first atom's frac_coords with
  sympy.Rational(x).limit_denominator(12). A script installs the solution and runs it on every
  CIF; a decision judges the batch; problems go to a targeted repair.

trigger_when:
  - A task asks for Wyckoff position multiplicities and/or coordinates of the first atom of each Wyckoff position from CIF files.
  - A task asks for a function such as analyze_wyckoff_position_multiplicities_and_coordinates(filepath) over a folder of CIFs (e.g. /root/cif_files) written to a solution file (e.g. /root/workspace/solution.py).
  - Batch crystallographic symmetry analysis of SHELX / XRD / Materials Project CIFs where outputs are Wyckoff letters and rational fractional coordinates.

do_not_use_when:
  - The task wants space group, lattice, coordination, phase diagrams, band structures, or format conversion only, with no Wyckoff output; use pymatgen directly.
  - The task wants "4a"-style Wyckoff symbols per symmetry orbit (equivalent-site groups) rather than letters with per-letter atom totals.
  - The input is a molecule (no lattice) rather than a periodic crystal.

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - pymatgen
    - sympy

steps:
  - name: install-solution
    kind: execution
    description: >
      Copy scripts/wyckoff_solution.py to solution_path (creating its folder), import the
      installed copy, and run its entry function analyze_wyckoff_position_multiplicities_and_coordinates
      on every *.cif in cif_dir. Per file it records the output, the detected space group, the
      space group the CIF declares, and the atom count; it reports convention violations as
      errors (exception, empty result, keys not bare letters, non-int multiplicity, coordinates
      not 3 fraction strings, denominator > 12, multiplicities not summing to the atom count)
      and oddities as warnings (coordinate rounding to "1", only P1 found, partial occupancy).
      Use the container paths from the task statement; the defaults are cif_dir=/root/cif_files
      and solution_path=/root/workspace/solution.py.
    inputs:
      - name: cif_dir
        type: string
        description: Absolute path of the folder holding the CIF files, e.g. /root/cif_files.
      - name: solution_path
        type: string
        description: Absolute path where the solution module must be written, e.g. /root/workspace/solution.py.
    script: scripts/install_and_check.py
    timeout: 900
    outputs:
      - name: solution_written
        type: string
        description: Path of the installed solution module.
      - name: batch_results
        type: object
        description: "File name -> {output, symbol, number, num_sites, is_ordered, declared_space_group}; output is exactly what the entry function returned."
      - name: batch_errors
        type: list[*]
        description: "[{file, error}] for every file that failed or broke an output convention."
      - name: batch_warnings
        type: list[*]
        description: "[{file, warning}] for results that are legal but worth a look."
    inputs_to: review-batch

  - name: review-batch
    kind: decision
    description: Judge whether the installed solution can be handed in as is or needs a code repair.
    inputs:
      - name: batch_results
        type: object
      - name: batch_errors
        type: list[*]
      - name: batch_warnings
        type: list[*]
    questions:
      solution_verdict:
        type: choice
        instructions: >
          Can the installed solution be submitted unchanged? Any entry in batch_errors means
          repair. Judge warnings against these facts: CIFs written by pymatgen/Materials Project
          declare "P 1" and list the whole cell, so declared P1 with a higher detected group is
          normal; a coordinate of "1" comes from a fractional coordinate just below 1.0 and is the
          reference convention, not a defect; "only P1 found" is fine when the CIF itself declares
          P1 and there is no sign of a higher group, but suspicious when the CIF declares a higher
          group (noisy coordinates; needs a tolerance retry); partial occupancy is acceptable when
          the output is non-empty and convention-compliant. Rounding like 0.385 -> 3/8 is the
          intended approximation, never a reason to repair.
        criteria:
          accept: batch_errors is empty and every warning is explained by the facts above; every file has non-empty, letters-only, int-multiplicity, fraction-string output.
          repair: batch_errors is non-empty, or a warning signals a wrong result (e.g. only P1 found while the CIF declares a higher space group).
    thresholds:
      solution_verdict: 0.3
    inputs_to: by-verdict

  - name: by-verdict
    kind: router
    description: Accepted solutions are done; anything else goes to a targeted repair.
    branch_on: solution_verdict
    branches:
      accept: end
      repair: repair-solution

  - name: repair-solution
    kind: client_task
    description: >
      Fix the installed solution for the failing files with the smallest change, keeping the
      spglib method and output conventions, then re-run it on every CIF.
    inputs:
      - name: solution_written
        type: string
      - name: cif_dir
        type: string
      - name: batch_results
        type: object
      - name: batch_errors
        type: list[*]
      - name: batch_warnings
        type: list[*]
    template: assets/repair.md
    references:
      - path: references/wyckoff-method.md
        description: The reference method, output conventions, the wrong symmetrized-structure approach, gotchas, and a symptom -> fix table (CIF parse failures, occupancy tolerance, multiple data blocks, empty dataset, P1-only results). Load for every repair.
    outputs:
      - name: repair_notes
        type: string
        description: What failed, what was changed in the solution, and the per-file re-run outcome.
      - name: repaired_results
        type: object
        description: File name -> the entry function's output after the fix.
    inputs_to: end

  - name: end
    kind: end
    description: The solution module is installed at solution_written and was judged ready (directly or after repair).
    inputs:
      - name: solution_written
        type: string
      - name: solution_verdict
        type: string

anti_patterns:
  - Using get_symmetrized_structure().wyckoff_symbols or len(equivalent_sites) — gives "4a"-style labels per orbit and wrong per-letter totals; use get_symmetry_dataset().wyckoffs, one letter per atom.
  - Reporting "4a"/"8c" keys instead of bare letters, or multiplicity per orbit instead of total atoms on the letter.
  - Taking coordinates from any atom other than the first atom (structure order) on the letter, or from the conventional/primitive standard cell instead of the structure as read.
  - Rounding with floats, round(), or nsimplify instead of sympy Rational(x).limit_denominator(12); returning numbers instead of strings like "1/2".
  - Wrapping a "1" coordinate to "0", or loosening symprec for files that already work — both change the reference answers.
  - Hardcoding any file's answer, or reading the expected output from the example in the task statement.
  - Installing extra packages; the container has only pymatgen 2025.10.7 and sympy 1.14.0 on Python 3.12.
```
