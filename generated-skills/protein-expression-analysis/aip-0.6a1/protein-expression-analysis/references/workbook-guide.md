# Protein-expression workbook guide

Load this when the layout detection is wrong or incomplete, when `fill_workbook.py`
reports issues, or when you must repair the workbook by hand.

## The task in spreadsheet terms

| Block | Target cells (standard instance) | What goes there |
|---|---|---|
| Lookup | Task `C11:L20`: rows = 10 target proteins (Protein_ID in col A, gene in col B), columns = 10 samples (names in row 10, group in row 9) | Two-way lookup of the Data value for (protein, sample) |
| Statistics | Task `B24:K27`, **transposed**: column B = protein in row 11, C = row 12, … K = row 20; rows 24/25/26/27 = Control Mean / Control StdDev / Treated Mean / Treated StdDev | Mean and sample stdev over that protein's Control and Treated columns |
| Fold change | Task `C32:D41`, rows in the same protein order as rows 11–20; **C = Fold Change, D = Log2 FC** (Fold Change comes first) | Log2 FC = Treated Mean − Control Mean; FC = 2^Log2 FC |

Data sheet: row 1 headers `Protein_ID | Gene_Symbol | Description | <sample columns…>`,
one protein per row (200 × 50 in the standard file). Values are already log2, so a
plain mean/stdev is correct and the fold change is a difference, not a ratio.

## Formulas the script writes (missing_value_policy = exclude)

```
Lookup  C11: =IF(INDEX(Data!$A$2:$BA$201,MATCH($A11,Data!$A$2:$A$201,0),MATCH(C$10,Data!$A$1:$BA$1,0))="","",INDEX(...same...))
Mean    B24: =IF(COUNT(C11:G11)=0,"",AVERAGE(C11:G11))
StdDev  B25: =IF(COUNT(C11:G11)<2,"",STDEV(C11:G11))
Log2FC  D32: =IF(COUNT(B26,B24)<2,"",B26-B24)
FC      C32: =IF(D32="","",2^D32)
```

- Group columns come from the group row labels, not from position; non-contiguous
  groups use a union (`C11,E11,H11`).
- `STDEV` (= sample stdev, STDEV.S) is used because it needs no `_xlfn.` prefix and
  works in Excel, LibreOffice and Gnumeric.
- Sample-name matching: exact header match; else `TRIM(C$10)`; else, when the Task
  name is a unique substring of one Data header (prefixed headers such as
  `MDAMB468_BREAST_TenPx01`), `MATCH("*"&C$10&"*",…,0)`.
- Protein matching: by Protein_ID; falls back to Gene_Symbol only when the ID is
  absent and the gene is unique in Data.

## Missing measurements

The Data sheet has blank cells (proteins not quantified in a sample). A bare
`INDEX/MATCH` on a blank returns **0**, and 0 on a log2 scale is a real value
(ratio 1) — it silently drags means toward 0 and inflates stdevs. Default policy
`exclude` keeps blanks blank so AVERAGE/STDEV use observed values only; a group with
0 observed values gets a blank mean, < 2 gets a blank stdev, and the fold change is
blank when either mean is blank. Use `zero` only when the task statement explicitly
says to treat missing values as 0.

## Gotchas

- The Task sheet's own instruction text (rows 3–7: "H7:BB16", "H19:BB28", "Step 4 …
  top regulated proteins") is stale and does not match the real yellow cells. Follow
  the task statement and the yellow fills; do not do a "Step 4".
- `A32:B41` (Protein_ID / Gene for the fold-change block) are blank and not yellow;
  leave them unless the task asks for them.
- Only the yellow cells are inputs. Do not touch fills, fonts, number formats, merged
  cells, sheet order, or the Data sheet. Never add macros/VBA.
- openpyxl writes formulas without cached values. Recalculate with LibreOffice
  (`python scripts/recalc.py <file> 120`) so readers see numbers. Never open with
  `data_only=True` and save — that replaces every formula with its value permanently.
- recalc.py writes a macro into the LibreOffice user profile (`~/.config/libreoffice`
  on Linux) on first run; the first run can take ~30 s.

## Repair checklist (when verdict = needs_attention)

1. `Recalculation failed`: confirm `soffice` is on PATH; rerun
   `python scripts/recalc.py <output_path> 180` from the skill's `scripts/` folder.
   If LibreOffice is truly unavailable, the file still holds correct formulas; say so.
2. `#N/A` / unresolved protein or sample: inspect the Data headers / IDs for the
   name; fix with a `layout_overrides` entry (e.g. `sample_resolution`) and rerun the
   fill, or edit that formula — never type the number in. If the protein or sample is
   genuinely absent from Data (no ID, gene or header matches), keep the lookup formula
   but wrap it as `=IFERROR(<lookup>,"")` for that row/column only, so the sheet has zero
   errors and the statistics for it stay blank (COUNT ignores the gap); report the
   absent name.
3. `values differ`: compare `fill_report.mismatches` against the Data sheet; usually a
   wrong group assignment or a shifted stats/fold-change cell list.
4. `style drift`: LibreOffice re-saved fills/fonts differently. The untouched-style
   copy is `fill_report.formulas_only_copy`; prefer it if the drift is visible
   (colours/fonts), keep the recalculated file if the drift is cosmetic-only.
5. Re-verify: reopen with openpyxl (formulas) and with `data_only=True` (values,
   read-only), check every yellow cell holds a formula and no cell shows `#…` errors.

## Layout override format

`layout_overrides` is shallow-merged into `detected_layout` (nested dicts merged one
level). Common keys:

```json
{"groups": {"C": "Control", "D": "Treated"},
 "stats_cells": {"control_mean": ["B24", "C24"], "control_sd": ["B25", "C25"],
                 "treated_mean": ["B26", "C26"], "treated_sd": ["B27", "C27"]},
 "fc_cells": {"fold_change": ["C32", "C33"], "log2_fc": ["D32", "D33"]},
 "sample_resolution": {"C": {"name": "X", "by": "contains", "data_header": "X_LUNG_TenPx01"}}}
```

Lists are per target protein, in `lookup.target_rows` order.
