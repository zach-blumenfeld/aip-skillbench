# Correct the template layout before formulas are written

`inspect` could not map the workbook cleanly. Fix the `layout` object by hand so `build` writes every formula into the right cells.

Workbook: {workbook_path}
Task instructions: {task_instructions}

Detected layout:
{layout}

Warnings:
{layout_warnings}

Instruction text found on the sheet:
{sheet_instructions}

Do this:
1. Open the workbook with openpyxl (pandas is not installed in the task container) and look at the task sheet yourself: the yellow-filled cells (fill FFFF00) are the cells to fill, the row labels in column A name each statistic, and the light-blue header rows name the columns.
2. Trust, in this order: the task instructions you were given, then the yellow cells and row/column labels, then the instruction text on the sheet. Sheet instruction ranges are often stale (shifted rows/columns); never write into a range only because a sheet instruction names it.
3. Edit only the keys that are wrong. Column references are letters; row references are integers. Keys:
   - `task_sheet`, `data_sheet`; `header_row` (row holding Protein_ID and the sample names), `id_col`, `gene_col`
   - `protein_rows` (one per protein, top to bottom), `control_cols`, `treated_cols` (sample columns in the lookup block; they may be interleaved)
   - `stats_header_row`, `stats_rows` (keys `control_mean`, `control_sd`, `treated_mean`, `treated_sd` → row), `stat_cols` (one column per protein, same order as `protein_rows`)
   - `fold_change`: `header_row`, `rows` (same order as `protein_rows`), `id_col`, `gene_col`, `fc_col`, `log2_col`
   - `top_table`: `title_row`, `header_row`, `first_row`, `existing_template`; or null when no ranking section is wanted
   - `data`: `header_row`, `first_row`, `last_row`, `id_col`, `first_value_col`, `last_col` on the data sheet
4. If the task asks for a group other than Control/Treated (e.g. a third condition), map the two groups the task compares into `control_cols` (baseline) and `treated_cols`.

Return the corrected `layout` object, plus `data_scale`, `stdev_kind`, and `add_top_table` unchanged unless your inspection shows they were wrong.
