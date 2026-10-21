# Source and provenance: protein-expression-xlsx

## Inputs compiled

| File | Origin | Use |
|---|---|---|
| `xlsx/SKILL.md` | curated `xlsx` skill (verbatim copy) | workbook editing rules, recalc workflow, verification checklist |
| `xlsx/recalc.py` | curated `xlsx` skill (verbatim copy) | LibreOffice recalculation; adapted copy in `scripts/recalc.py` |
| `xlsx/LICENSE.txt` | curated `xlsx` skill (verbatim copy) | licence terms of the source material |

Domain context (not copied: it lives in the task, not in a skill): the task statement
(`instruction.md`: lookup C11:L20, stats rows 24-27 cols B-K, FC/log2FC C/D rows 32-41,
log2 data, formulas only, keep formatting, no VBA) and the real `protein_expression.xlsx`
(Task + Data sheets, 200 proteins x 50 samples in Data!A1:BA201, 2,112 blank Data cells,
17 blanks among the 100 target lookups, three protein/group pairs with < 2 measured values).

## Intent

One coherent unit: fill the protein-expression template with live formulas, recalculate,
and prove the result. The general xlsx skill supplies the "formulas not hardcodes / zero
errors / preserve template / recalc" discipline; the distilled skill turns it into a
layout-detecting fill script and an independent verifier for this task type.

## Component kinds

| Component | Kind | Why |
|---|---|---|
| 1. Inspect layout | execution (`protein_task.py inspect`) | Layout detection from labels, group mapping, name-matching mode and missing-value counts are deterministic over the workbook. |
| 2. Missing-value policy | decision (`missing_policy`, choice exclude/zero) | Depends on reading the task statement; answer space is fixed; feeds the fill/verify `--missing` flag. |
| 3. Write formulas | execution (`protein_task.py fill`) | Formula construction (INDEX/MATCH, AVERAGE/STDEV, log2FC, 2^x) is pure rule application; scripting it removes off-by-one and transposition mistakes. |
| 4. Recalculate | execution (`recalc.py`) | Mechanical LibreOffice run, from the source skill. |
| 5. Verify | execution (`protein_task.py verify`) | Replaces the source's prose verification checklist with code: formula presence, error scan, independent recomputation, untouched non-target cells/styles. |
| 6. Report | client_task | Free-text summary for the user. |

Kept as a single `protein_task.py` with subcommands (shared layout detection) plus the
independent `recalc.py`.

## Adaptations

- `scripts/recalc.py`: the first-run `soffice --terminate_after_init` call is wrapped so a
  slow first start (>10 s) no longer raises `TimeoutExpired` (timeout raised to 60 s), and
  a missing `soffice` returns JSON instead of a traceback. Otherwise identical.
- `references/xlsx-guide.md`: the source SKILL.md body with `python recalc.py` paths
  rewritten to `python3 scripts/recalc.py` and a header noting pandas is absent in the
  task container and template conventions override its formatting rules.
- Missing data: the source says nothing; the instruction suggests INDEX/MATCH, which turns
  blanks into 0. The skill defaults to keeping blanks blank and excluding them from the
  statistics (scientifically correct for log2 data), with an explicit `zero` branch.
  STDEV of a single value yields "" instead of `#DIV/0!` to satisfy the zero-errors rule.

## Source coverage (line-by-line check)

| Source content | Where in the skill |
|---|---|
| Zero formula errors | fill guards (COUNT/IF), recalc error scan, verify error check, step 5 gate |
| Preserve existing templates / match format | fill writes only target cells; verify non-target + style check; Gotchas last bullet |
| Financial-model colour coding, number formats, assumptions placement, hardcode documentation | `references/xlsx-guide.md` (template conventions override; not applied to this template) |
| LibreOffice required; recalc auto-configures macro | compatibility, "Before you start", step 4 |
| pandas reading/analysis | `references/xlsx-guide.md` (pandas absent in container, noted) |
| Use formulas, not hardcoded values (WRONG/CORRECT examples) | step 3 formulas; verify "not a formula"; Gotchas |
| Common workflow 1-6 (choose tool, load, modify, save, recalc mandatory, verify/fix errors) | Workflow steps 1-5 |
| Error types #REF!/#DIV/0!/#VALUE!/#NAME? and fixes | recalc JSON in step 4, verify step 5 fix list, xlsx-guide |
| Creating new files (openpyxl Workbook, fonts/fills) | `references/xlsx-guide.md` |
| Editing existing files (load_workbook, sheets, modify) | `fill` implementation; xlsx-guide |
| recalc.py usage, timeout arg, behaviour | step 4 command `... 60` |
| Verification checklist: sample references, column mapping, row offset, NaN handling, multiple matches, div-by-zero, wrong refs, cross-sheet refs, start small, dependencies, edge cases | automated in `verify` (every cell recomputed independently, blanks/NaN, n<2), `inspect` (unique-match check, layout), Gotchas (blank→0) |
| Interpreting recalc.py JSON | step 4; xlsx-guide |
| Library selection; openpyxl 1-based, data_only warning, read_only/write_only, formulas not evaluated | Gotchas (data_only, cached values); xlsx-guide |
| pandas dtype/usecols/parse_dates tips | xlsx-guide |
| Code style (minimal Python, few prints) | scripts follow it; xlsx-guide |
| Cell comments / document hardcode sources | xlsx-guide (no hardcodes are written, so nothing to document) |

## Deliberate drops

- Financial-model sections (colour coding, currency/year/percentage/multiple formats,
  assumption cells, source citations for hardcodes) are not applied in the body: the
  protein template has established conventions, which the source itself says override
  these guidelines, and the task forbids format changes. Kept verbatim in
  `references/xlsx-guide.md`, not lost.
- LICENSE.txt terms: legal text, not actionable; kept in `source/xlsx/LICENSE.txt`.
- Windows/macOS `timeout`/`gtimeout` branches of recalc.py: kept in code, not described
  in the body (the container is Ubuntu).
