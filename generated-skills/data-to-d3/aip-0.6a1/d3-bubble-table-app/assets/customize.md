# Extend the generated D3 web app to cover what the task asks beyond the default build

The default build already wrote a working app to `{output_dir}`:
`index.html`, `css/style.css`, `js/d3.v6.min.js`, `js/visualization.js`, and a verbatim copy of the input data under `data/`.
`js/visualization.js` already holds `PRICE_FILES` (upper-case ticker -> app-relative price CSV path) for any panel that needs the per-ticker files.
It renders a sector-clustered bubble chart (area ~ market cap, uniform size for rows without a market cap) beside a linked table
(Ticker symbol / Full company name / Sector / Market cap), with tooltips and two-way click highlighting.

Task statement:

{instruction}

What the data looks like:

{data_profile}

What the build produced:

{build_report}

Do this:

1. List every requirement in the task statement that the default app does not satisfy (extra charts, different encodings, other columns, other formats, different layout). Only those; do not rework what already meets the task.
2. Edit the files in `{output_dir}` in place to satisfy them. Keep D3 v6 loaded from `js/d3.v6.min.js` (no CDN), keep the file layout the task names, and keep everything the default app already does unless the task contradicts it: one bubble per row, ticker label in each bubble, legend per sector, forceX/forceY sector clusters plus forceCollide, no overlap, tooltip only for rows with market cap, `selected` class linking bubble and row both ways, the embedded-rows fallback for file:// opening.
3. Stay deterministic: no Math.random, no transitions; fixed sizes; stop the simulation and tick a fixed count.
4. Load `references/app-structure.md` before editing `visualization.js` (function map, classes, data attributes, how to add a panel). Load `references/d3-patterns.md` for tooltip, click-linking and determinism patterns. Load `references/price-history-files.md` if the change reads the per-ticker price CSVs.
5. Open the page yourself (headless browser or the verify script: `python3 scripts/verify_app.py --data-dir <data_dir> --output-dir {output_dir}` from the skill folder) and fix anything you broke before answering.

Answer with `customizations`: one short string per change, naming the requirement and the file(s) edited.
