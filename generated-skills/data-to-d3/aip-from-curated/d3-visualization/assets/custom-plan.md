Plan a hand-written D3 page for a chart the bubble generator does not cover.

Task request (verbatim):
{task_request}

Data profile:
{data_profile}

Output folder the task named (or your default): {output_dir}

Decide, from the task (defaults in brackets, record each default you take):
- chart type and encodings: x/y fields, aggregation, sort/filter rules, color rule (categorical: d3.schemeCategory10 over the sorted domain; sequential: a d3.interpolate* scheme), labels/title/axis units [infer the best chart type for the data and question].
- dimensions and margins [800 x 600 with a viewBox of the same size; margin 20 for charts without axes, top 20 / right 20 / bottom 40 / left 60 when axes or tick labels need room].
- file layout: the exact paths the task names [under output_dir: chart.html, chart.svg, vendor/d3.v<version>.min.js, so the folder is self-contained].
- D3 version [the version the task names; else "6", which resolves to the bundled 6.7.0]. It is vendored locally; never a CDN.
- interactions the task asks for (tooltips, click highlighting, linked views) and which rows are excluded from them.

Return `page_manifest`:
`html_path` (absolute), `js_paths` (absolute, your own scripts), `css_paths` (absolute), `d3_path` (absolute path where D3 must be written, referenced by the HTML), `d3_version`, `svg_path` / `png_path` (absolute or null), and `expect` with what the verifier should test: `svg_selector`, `mark_selector`, `mark_count` (computed from the data profile, not guessed), `key_attr` (the data attribute carrying each mark's id, e.g. "data-key"), and when relevant `tooltip_selector`, `tooltip_included_keys`, `tooltip_excluded_keys`, `tooltip_contains_key` (default true: the hovered mark's key must appear in the tooltip text; set false when the task's tooltip omits it), `table_row_selector`, `table_row_count`, `linked`, `no_overlap` and `within_bounds` (both only check `<circle>` marks), `label_selector`.
Return BOTH keys: `page_manifest` and `chart_plan` (object: chart type, encodings, defaults taken). The next steps read both.
