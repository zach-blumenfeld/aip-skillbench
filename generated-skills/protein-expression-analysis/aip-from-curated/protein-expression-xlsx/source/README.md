# protein-expression-xlsx — provenance and compile log

## Sources
- `source/xlsx/SKILL.md` — Anthropic's curated `xlsx` Agent Skill (spreadsheet creation, editing, analysis, recalculation), copied verbatim.
- `source/xlsx/recalc.py` — its LibreOffice recalculation + error-scan script, copied verbatim; also copied unchanged to `scripts/recalc.py`, which `verify_workbook.py` imports.
- `source/xlsx/LICENSE.txt` — licence terms, verbatim.
- Task environment (read, not copied): `inputs/environment/Dockerfile` (Ubuntu 24.04, python3, LibreOffice, Gnumeric, openpyxl 3.1.5; **no pandas**) and `data/protein_expression.xlsx` (full file, 117,651 bytes).

## What the target workbook looks like (drove the design)
- Sheet `Task`: title, instruction lines in A3:A7 that quote ranges (`H7:BB16`, `H19:BB28`, `H31:L40`, `H43:L52`) which do **not** match the real template; row 9 "Sample Group:" with Control ×5 / Treated ×5; row 10 headers (Protein_ID, Gene_Symbol, 10 CCLE sample names); rows 11–20 ten proteins with yellow cells C11:L20; rows 24–27 Control Mean / Control StdDev / Treated Mean / Treated StdDev with yellow B24:K27 (one column per protein, transposed); rows 31–41 fold-change table with yellow C32:D41 (Fold Change, Log2 FC) and empty Protein_ID/Gene_Symbol cells; no Step 4 region.
- Sheet `Data`: 200 proteins × 50 CCLE TMT samples (D1:BA201), log2 relative abundances (min ≈ −15.2, max ≈ 7.0, 53 % negative), 21 % blank cells; four of the ten task proteins have blanks in their task samples, two have only one value in a group.

## Step-kind choices
| Step | Kind | Why |
|---|---|---|
| inspect | execution | Locating yellow cells, labelled rows, sample groups, data bounds and missing counts is deterministic over the file. Detection is label/fill-driven, not hardcoded, so other files of the same family work. |
| assess | decision | Four judgments with fixed answer spaces: data scale (log2/linear, from a script-made profile plus task wording), SD type (sample/population), whether a ranking is requested (noul), whether the layout is trustworthy (noul). Thresholds flag close calls on the costly ones. |
| layout-gate | router | Branch on `layout_ok`. |
| fix-layout | client_task | Correcting an unexpected layout needs the agent's own inspection; output is a structured `layout` object the build script consumes. |
| build | execution | Formula strings, guards and the shadow computation are deterministic given layout + decisions. |
| verify | execution | Recalc (recalc.py), error scan, formula-survival check and value comparison are deterministic. |
| verify-gate / after-fix | router | Branch on `verify_status` / `fix_outcome`. |
| fix-output | client_task | Diagnosing a failed recalc or mismatch is open-ended troubleshooting. Loops back to verify or ends as `unresolved`. |
| report | client_task | Free-text summary for the requester. |

## Method decisions (encoded in build_formulas.py)
- Lookups: `IFERROR(IF(INDEX(..)="","",INDEX(..)),"")` keyed on Protein_ID (row) and sample header (column). Plain INDEX returns 0 for blank cells, which would bias means; blanks stay blank.
- Stats: `AVERAGE`, `STDEV` (sample, legacy name to avoid `_xlfn.` #NAME? issues) or `STDEVP`, each guarded by `COUNT` so empty groups or n<2 give "" instead of #DIV/0!. Non-contiguous group columns are written as comma lists.
- Fold change: log2 data → Log2 FC = treated mean − control mean, FC = POWER(2, Log2 FC); linear data → FC = ratio, Log2 FC = LOG(FC, 2).
- Fold-change table Protein_ID/Gene_Symbol cells (empty, unfilled) and statistics header cells B23:K23 get reference formulas (`=A11`, `=B11`) so the transposed blocks are readable; only empty cells are touched.
- Step 4 (no template region): a ranking table two rows below the fold-change table — Protein_ID, Gene_Symbol, Log2 FC, |Log2 FC|, Rank (`COUNTIF(abs,">"&x)+COUNTIF(above,x)`, unique), Direction — plus a sorted strongest-first list in H:L via INDEX/MATCH on rank; all formulas, headers styled like the template's light-blue headers.
- SD needs at least 2 values for both sample and population SD (population SD of one value would be a misleading 0).
- Without LibreOffice, verify still checks that formulas are present and free of un-prefixed modern function names, and reports `recalc_unavailable`.
- Fresh-agent test feedback applied: guard before calling recalc.py when soffice is absent; Gnumeric noted as container-only; sorted ranking view; blank single-value population SD.
- Every written cell also gets a Python-computed expected value; verify compares LibreOffice's cached results against it.
- Recalculation: recalc.py first; if it errors, or exits cleanly but leaves cells uncached, verify retries with `soffice --headless --convert-to xlsx` (LibreOffice computes cells that have no cached value on load).

## Completeness check — source/xlsx/SKILL.md, line by line
| Source item | Where it lives now |
|---|---|
| Frontmatter description (create/edit/analyse/recalc xlsx) | SKILL.md description, trigger_when; references/xlsx-guide.md |
| License line | frontmatter `license`, source/xlsx/LICENSE.txt |
| Zero formula errors | verify step (error scan), verify-gate, anti_patterns, xlsx-guide |
| Preserve existing templates / match conventions / template overrides | anti_patterns (restyling), build (only empty/yellow cells, header style copied), xlsx-guide |
| Financial-model colour coding, number formats, assumptions placement, hardcode-source documentation | references/xlsx-guide.md "Financial-model conventions" (conditional; not applied to expression templates because template conventions override and these are not financial models) |
| Formula error prevention (references, off-by-one, consistent formulas, edge cases, circular refs) | build formulas (absolute refs, guards), xlsx-guide checklist, fix_output.md |
| LibreOffice required; recalc.py configures itself | scripts/recalc.py via verify; compatibility; fix_output.md |
| pandas reading/analysis snippets | xlsx-guide workflow step 1 (noted: pandas absent in the container; openpyxl used) |
| CRITICAL: formulas not hardcoded values (wrong/right examples) | build writes only formulas; anti_patterns; xlsx-guide |
| Common workflow 1–6 (choose tool, load, modify, save, recalc, verify/fix loop, error meanings) | build → verify → verify-gate → fix-output → verify loop; xlsx-guide; fix_output.md |
| Creating new files (Workbook, Font, PatternFill, Alignment, widths) | xlsx-guide workflow step 3; build uses Font/PatternFill for the ranking header |
| Editing existing files (load_workbook, sheets, insert/delete, create_sheet) | xlsx-guide workflow step 2; build |
| Recalculating formulas section (usage, timeout, what the script does) | verify (recalc(path, 90)); xlsx-guide; fix_output.md |
| Formula verification checklist (sample refs, column mapping, row offset, NaN, far-right columns, multiple matches, div/0, wrong refs, cross-sheet refs, start small, dependencies, edge cases) | inspect (ID/sample/duplicate checks), verify (full comparison), xlsx-guide checklist |
| Interpreting recalc.py output JSON | xlsx-guide; verify_report |
| Library selection, openpyxl 1-based indexing, data_only warning, read_only/write_only, formulas not evaluated | xlsx-guide "openpyxl facts"; anti_patterns (data_only save, uncalculated delivery) |
| pandas dtype/usecols/parse_dates tips | xlsx-guide workflow step 1 |
| Code style (concise Python; comment complex cells, document sources, note sections) | xlsx-guide "Style" |
| recalc.py (macro setup, soffice call, timeout handling, error scan, formula count) | scripts/recalc.py verbatim, called by verify_workbook.py |

## Deliberate drops
- recalc.py's CLI usage/help printing: not needed because verify imports `recalc()` directly; the CLI still works unchanged for manual repair.
- The source's generic pandas-first advice as a default: replaced by openpyxl because the task container does not install pandas (kept as a conditional note in the guide).
- No content dropped from the source's rules; financial-only conventions are retained in the reference, marked conditional.
