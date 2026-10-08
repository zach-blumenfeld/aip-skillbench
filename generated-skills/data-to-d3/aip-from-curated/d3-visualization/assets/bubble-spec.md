Write `viz_spec`: the JSON object the page generator (`scripts/build_bubble_page.py`) turns into a clustered bubble chart plus a linked, sortable data table, all offline and deterministic.

Task request (verbatim):
{task_request}

Data profile (from profile-data):
{data_profile}

Output folder the task named (or your default): {output_dir}

Previous build report, if this is a retry (fix every error it lists):
{build_report}

Fill the spec field by field from the task request. Anything the request does not say takes the default and is listed in the page's header comment.

1. `output`: `dir` = the folder the task wants. `html`, `js`, `css`, `d3` = the exact relative paths the task lists (defaults index.html, js/visualization.js, css/style.css, js/d3.v<major>.min.js). `d3_version` = the major (or exact) version the task names; if it names none use "6". `copy_data` = every input file or folder the task says to copy/ship with the app (absolute paths); they land under `data_dir` with their original names. `svg` / `png` = exported files only if the task asks for them (the source skill's dist/chart.svg convention applies when the task wants files but gives no layout).
2. `data.file` = the table with one row per entity (absolute path). `data.key` = its unique id column (the profile's `unique_text_columns`). Use real column names exactly as the profile shows them (spaces and case included, e.g. "full name").
3. `bubble.size_field` = the numeric column the task sizes by (sqrt scale, bigger value = bigger bubble). Rows missing it get `missing_radius` (uniform). `color_field` and `cluster_field` = the category the task colors and groups by (forceX/forceY pull each category to its own centre; collision keeps bubbles apart). `label_field` = the column shown on each bubble (usually the key); null for no labels. `legend: true` unless the task forbids a legend.
4. `tooltip.fields` = the fields the task wants on hover, in that order (first is bold). `tooltip.exclude` = rows that must get no tooltip. Rules: `{{"field", "equals"}}`, `{{"field", "in": [...]}}`, or `{{"field", "missing": true}}`. Check `data_profile.category_gaps`: a category whose numeric/text columns are all missing (e.g. a fund type with no size or country data) is usually the one the task excludes.
5. `table.columns` = the columns the task lists, with the header labels it gives, in its order. Numeric money/size columns use `"format": "abbrev"` (2 decimals + K/M/B/T, e.g. 1.64T); others: "number", "integer", "percent", "currency", "currency_abbrev", "text". `missing_text` is shown for empty cells (default "-"). Keep `sort_by` null to keep the file's row order.
6. `link: true` when clicking a bubble should highlight its row and clicking a row its bubble (both get classes `selected` and `highlighted`).
7. `series` = only when the task wants a per-entity time series (e.g. price history from a folder of per-key CSVs) shown on selection: `{{"dir": <abs folder>, "date_column": "Date", "value_column": "Close", "resample": "weekly"}}`. File names are matched to keys case-insensitively and missing columns fall back to Close. If the task names such a folder as data to visualize (e.g. "individual stock price histories") but describes no view for it, add the series anyway: it renders only below the chart on selection and leaves the requested views untouched. If the folder is only to be copied, leave `series` null.
8. `layout`: "side-by-side" (chart left, table right) or "stacked".

Example of a complete spec (different dataset; mirror its shape, not its values):
{assets[bubble-spec-example]}

Return `viz_spec` (object). Keep `data_profile` and the other state keys unchanged.
