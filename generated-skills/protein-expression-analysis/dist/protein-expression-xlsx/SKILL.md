---
name: protein-expression-xlsx
description: Fill a proteomics Excel template with live formulas - two-way INDEX/MATCH lookup of log2 protein expression values (protein ID x sample name) from a Data sheet, Control vs Treated mean and standard deviation, log2 fold change and fold change - then recalculate with LibreOffice and verify values, zero formula errors, and untouched formatting. Use for protein_expression.xlsx-style tasks (Task + Data sheets, yellow cells to fill, cancer cell line control/treated comparisons) or any openpyxl workbook-template fill that must keep formulas instead of hardcoded numbers.
compatibility: Python >= 3.8 with openpyxl (3.1.x); LibreOffice (`soffice` on PATH) for recalculation. No pandas needed. Scripts - scripts/protein_task.py (openpyxl), scripts/recalc.py (openpyxl + soffice).
---

# Protein Expression Workbook (lookup, group stats, fold change)

## Trigger When

- A task hands you `protein_expression.xlsx` (sheets "Task" and "Data") and asks for expression lookups, Control/Treated statistics, or fold changes in yellow cells.
- Any quantitative-proteomics or expression spreadsheet where values must be pulled by protein ID x sample name into a template and summarised per group with formulas.
- Filling an existing Excel template with formulas where format, colours, and fonts must stay intact and the file must be recalculated with zero formula errors.

## Purpose

Turns the template into a live, formula-driven analysis: detects the Task/Data layout from its labels (no hardcoded cell positions beyond what the labels define), writes INDEX/MATCH lookups, per-group AVERAGE/STDEV and log2FC/FC formulas, recalculates with LibreOffice, and independently re-computes every target value from the Data sheet to prove the cached results, the formula-only rule, and the untouched formatting. It adds the gotchas a general spreadsheet agent misses: blank Data cells silently become 0 through INDEX, the Task sheet's own instruction text names stale ranges, the statistics block is transposed, and openpyxl saves drop all cached values.

## Before you start

Check the requirements: `python3 -c "import openpyxl"` and `which soffice`. Name everything missing before running any script. Run all commands from this skill's folder (or prefix the script paths with it). Work on the task's file in place (e.g. `/root/protein_expression.xlsx`) but keep an untouched copy for verification.

## Workflow

Progress:
- [ ] 1. Inspect layout (script)
- [ ] 2. Decide the missing-value policy (decision)
- [ ] 3. Write formulas (script)
- [ ] 4. Recalculate (script)
- [ ] 5. Verify, fix, repeat (script)
- [ ] 6. Report (client task)

### 1. Inspect (execution)

```bash
cp /root/protein_expression.xlsx /tmp/protein_expression.orig.xlsx
python3 scripts/protein_task.py inspect /tmp/protein_expression.orig.xlsx
```

Input: workbook path (string). Output JSON (object): `lookup_range` (C11:L20 here), `control_columns`/`treated_columns` (read from the "Control"/"Treated" labels in the row above the sample header, never assumed contiguous), `stats_range` (B24:K27; one column per protein in target order: B = first protein row, C = second, ...), `fold_change_cells`/`log2fc_cells` (column chosen by header text "Fold Change" vs "Log2 FC"), `sample_match`/`protein_match` (`exact`, `trim`, `contains`, or `unmatched`), `already_filled_targets`, per-protein missing cells and `groups_with_fewer_than_2_values`.

- `status: error` with `unmatched_*`: a Task name has zero or several Data matches. Read the listed candidates, fix nothing in the template, and resolve by hand only if the task text tells you the naming rule; otherwise report it.
- `already_filled_targets` non-empty: those target cells hold something now. Step 3 overwrites them; do so only if they are placeholders or stale values (target cells must end up as formulas).
- Exit 1 with a layout message (missing "Protein_ID" header, statistic labels, or group row): the template differs from the expected shape; read the Task sheet and map the cells yourself, following the formula patterns in step 3.

### 2. Missing-value policy (decision)

Input: the task statement plus `total_missing_lookup_cells` from step 1.

```yaml
missing_policy:
  type: choice
  instructions: How must a blank (missing) expression value in the Data sheet be treated in the lookup grid and the statistics?
  criteria:
    exclude: Default. The task says nothing about missing values, or says to ignore/skip/exclude them. Blank stays blank (""), means/SDs use only the measured values.
    zero: The task explicitly says missing values count as 0 (or to impute 0).
```

Choose `exclude` unless the statement explicitly asks for zero; a wrong `zero` silently drags log2 means toward 0 (log2 = 0 is "average", not "absent"), so reconsider any close call that leans `zero`.

### 3. Write formulas (execution)

```bash
python3 scripts/protein_task.py fill /tmp/protein_expression.orig.xlsx /root/protein_expression.xlsx --missing <missing_policy>
```

Writes only the target cells; every other cell, fill, font, and the Data sheet are left as loaded. Formula patterns it emits (rows/columns follow the detected layout):

| Cell block | Formula (first cell, `exclude`) |
|---|---|
| Lookup C11:L20 | `=IF(INDEX(Data!$A$1:$BA$201,MATCH($A11,Data!$A$1:$A$201,0),MATCH(C$10,Data!$A$1:$BA$1,0))="","",INDEX(...same...))` (`zero`: `=N(INDEX(...))`) |
| Control mean / SD (B24, B25) | `=IF(COUNT(C11:G11)>=1,AVERAGE(C11:G11),"")`, `=IF(COUNT(C11:G11)>=2,STDEV(C11:G11),"")` |
| Treated mean / SD (B26, B27) | same over the treated columns of that protein's row |
| Log2 FC (D32) | `=IF(OR(B24="",B26=""),"",B26-B24)` = Treated Mean - Control Mean |
| Fold Change (C32) | `=IF(D32="","",POWER(2,D32))` = 2^Log2FC |

Rules baked in: exact-match MATCH (`0`), absolute ranges bounded to the Data table, sample SD (`STDEV`, n-1; the data are already log2 so plain mean/SD are correct, never re-log), non-contiguous groups become cell lists (`STDEV(C11,E11,G11)`), `trim`/`contains` name matches use `TRIM(...)` / `"*"&TRIM(C$10)&"*"`. A group with one measured value has no defined SD and gets "" instead of `#DIV/0!`.

### 4. Recalculate (execution)

```bash
python3 scripts/recalc.py /root/protein_expression.xlsx 60
```

openpyxl writes formulas without cached values; a grader reading values sees nothing until LibreOffice recalculates and saves. Output JSON: `status` `success` or `errors_found` with `error_summary` locations; `{"error": ...}` means LibreOffice did not run (re-run once; the first run builds the LibreOffice profile). If it keeps failing, fall back to `ssconvert --recalc /root/protein_expression.xlsx /tmp/recalc.xlsx` (gnumeric) and copy back, then rely on step 5 to catch any style damage. For recalc JSON details, read `references/xlsx-guide.md`.

### 5. Verify (execution)

```bash
python3 scripts/protein_task.py verify /tmp/protein_expression.orig.xlsx /root/protein_expression.xlsx --missing <missing_policy>
```

Checks every target cell is a formula, has no error value, and that its cached value equals an independent Python computation from the Data sheet (tolerance 1e-6; blanks where data are missing); that no non-target cell value, merged range, or sheet name changed; that there is no VBA. `status: ok` exit 0 is the gate. On `errors_found`:
- "no cached value": you saved with openpyxl after recalculating; run step 4 again.
- "not a formula": a value was hardcoded; rerun step 3 then step 4.
- "value ... != expected": wrong reference or group mapping; re-inspect, fix, rerun 3 → 4 → 5.
- "non-target cell changed": restore from `/tmp/protein_expression.orig.xlsx` and redo from step 3.
`style_warnings` are non-fatal but must be explained: any change on a cell you touched is a bug; changes that appear only after step 4 are LibreOffice re-save artifacts (compare with the step-3 file to confirm).

### 6. Report (client task)

Tell the user: the file path, the missing-value policy and why, which proteins had blank statistics (from `groups_with_fewer_than_2_values`), and the proteins with the largest |log2FC| (read cached values with `load_workbook(path, data_only=True)`), noting that significance testing was not requested unless the task asked for it.

## Gotchas

- The Task sheet's own instruction lines (A4:A7, e.g. "H7:BB16", "H43:L52") are stale and do not match the yellow cells; follow the task statement and the labels the script detects. There is no "top regulated proteins" block to fill.
- Statistics are transposed: proteins run across columns B..K, statistics down rows 24-27.
- Fold-change table: column C is "Fold Change", column D is "Log2 FC" (FC is computed from Log2 FC, not the other way round). Columns A/B of rows 32-41 are not yellow; leave them.
- `INDEX` of a blank cell returns 0 in Excel/LibreOffice; without the `IF(...="","",...)` wrapper missing values enter the means as zeros.
- Never open with `data_only=True` and save: formulas are replaced by values permanently. Use `data_only=True` only to read.
- Every openpyxl save drops all cached values, so recalculate after the last save, and verify after recalculating.
- Data sample headers are full names like `MDAMB468_BREAST_TenPx01`; match on the full string. Partial names are risky: a plex suffix such as `TenPx02` is shared by several samples, so the script accepts a `contains` match only when it is unique.
- No macros/VBA, no new sheets, no changed fills/fonts/number formats; keep the `.xlsx` extension.
