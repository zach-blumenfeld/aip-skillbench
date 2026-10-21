Task statement:
{task_instruction}

Detected layout:
{detected_layout}

Warnings:
{layout_warnings}

Layout matches the task statement: {layout_matches_task}

If the layout matches, answer layout_overrides as an empty object. Otherwise answer only
the keys that must change, using the same shapes as the detected layout (groups maps a
sample column letter to Control or Treated; stats_cells and fc_cells hold one cell
address per target protein in lookup.target_rows order; sample_resolution and
protein_resolution entries carry by/data_header or by/data_row). Read the workbook
yourself with openpyxl if you need to check a cell. Remember: the statistics block is
transposed (one protein per column), the fold-change block puts Fold Change before
Log2 FC, and only yellow cells are targets. Never put numbers you computed into the
overrides; they describe where formulas go, not values.
