The batch check of `{solution_written}` (skill `{meta.name}`) found problems that need a code fix.

Errors (must be fixed):
{batch_errors}

Warnings:
{batch_warnings}

Per-file results so far (detected space group, declared space group, output):
{batch_results}

Do this:
1. Read `references/wyckoff-method.md` and match each error to a repair recipe.
2. Edit `{solution_written}` with the smallest change that fixes the failing files. Keep the entry
   function `analyze_wyckoff_position_multiplicities_and_coordinates(filepath: str)`, the spglib
   `get_symmetry_dataset().wyckoffs` method, letters-only keys, int multiplicities, and
   `Rational(x).limit_denominator(12)` strings. Never hardcode a file's answer.
3. Re-run the function on every CIF in `{cif_dir}` (e.g. `python3 {solution_written} {cif_dir}/*.cif`).
   Files that passed before must give identical output; failing files must now give non-empty,
   convention-compliant output, or you must state why the file cannot be analyzed.
4. Answer with `repair_notes` (what failed, what you changed, re-run outcome per file) and
   `repaired_results` (file name -> the function's output after the fix).
