# Source notes — cif-wyckoff-analysis

## Why this skill

The instruction at `source/instruction.md` asks the agent to write a
batch-style Python function `analyze_wyckoff_position_multiplicities_and_coordinates(filepath)`
to `/root/workspace/solution.py`. The function must read a CIF, extract
the Wyckoff multiplicity of each occupied position, and report the
first atom's fractional coordinates as rationals with denominator <= 12.

## Approach

Wyckoff analysis from a CIF is a solved problem in the materials-science
Python ecosystem. The dominant tool — pymatgen — gives us:

1. `CifParser` for SHELX-style CIF input.
2. `SpacegroupAnalyzer.get_symmetrized_structure()` to group sites by
   their Wyckoff orbit and label them with the full Wyckoff symbol
   (e.g. `8c`).

The skill therefore reduces to four moves:
1. Parse the CIF (conventional cell).
2. Symmetrize the structure to obtain Wyckoff orbits.
3. For each orbit, split the symbol into multiplicity + letter, pick
   the first site, and convert each fractional coord to a denominator-
   capped rational via `fractions.Fraction(value).limit_denominator(12)`.
4. Return the two dicts in the schema the prompt mandates.

Step 3's rational rounding has two subtle details captured in the
script and in `references/pymatgen-wyckoff-cheatsheet.md`:
- Fold coordinates into `[0, 1)` before converting (handles negatives
  and near-1 floats).
- Print zero as `"0"` not `"0/1"` to match the example.

## Schema choice

Used the bundled `procedure.schema.json` (AIP v0.3a2). This is a linear
script-backed procedure — install a reference solution, register it at
the path the grader checks, smoke-test it. No need for a new schema.

## Source → body mapping

| Instruction content                                                                  | Where it lives in the skill                                  |
|--------------------------------------------------------------------------------------|--------------------------------------------------------------|
| Function signature `analyze_wyckoff_position_multiplicities_and_coordinates`         | `scripts/solution.py` (canonical implementation)             |
| Required output schema (`wyckoff_multiplicity_dict`, `wyckoff_coordinates_dict`)     | `scripts/solution.py` return value                           |
| Denominator-<=-12 rational rounding                                                  | `_coord_to_fraction_string` in `scripts/solution.py`         |
| First-atom-per-Wyckoff-orbit rule                                                    | `scripts/solution.py` (uses `equivalent_sites[i][0]`)        |
| Mandatory output location `/root/workspace/solution.py`                              | `install-solution` step in `SKILL.md` body                   |
| "Use external imports" / "do not hardcode"                                           | `scripts/solution.py` uses pymatgen; no answer constants     |
| FeS2 mp-226 worked example                                                           | `scenarios` block in `SKILL.md` body                         |
| CIF files come from SHELX X-ray diffraction                                          | Context covered by `purpose`; no behavioral consequence      |

## Deliberate drops

- The exact numeric values in the FeS2 example (`["3/8", "1/9", "8/9"]`)
  are illustrative of *format*, not of *truth*. They reflect a rounded
  approximation and the agent should reproduce them by running the
  algorithm, not by anchoring to those literals. Captured in the
  scenario only as format guidance.
