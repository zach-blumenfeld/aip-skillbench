---
name: d3js-visualization
description: Build deterministic, verifiable data visualizations with D3.js (v6). Generate standalone HTML/SVG (and optional PNG) from local data files without external network dependencies. Use when tasks require charts, plots, axes/scales, legends, tooltips, or data-driven SVG output.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires a local D3 build vendored next to the output (default `vendor/d3.v7.9.0.min.js`); the network MUST NOT be assumed available. Python 3 is required for the determinism validator script.
---

```yaml
purpose: >
  Turn structured local data (CSV/TSV/JSON) into reproducible D3.js
  visualizations whose output bytes are stable across runs and
  machines. Default outputs are a self-contained `dist/chart.html` and
  a diff-friendly `dist/chart.svg`. Determinism — no randomness, no
  default transitions, vendored D3, stable IDs, fixed viewBox, rounded
  numerics — is non-negotiable; the procedure ends in a script-backed
  validation gate.

trigger_when:
  - User asks to make a chart, plot, graph, or visualization (bar, line, scatter, area, histogram, box, violin, heatmap, timelines, small multiples, facets).
  - User asks for axis ticks, scales, legends, tooltips, or data-driven SVG/HTML output for a report or web page.
  - User asks to convert a local data file (CSV/TSV/JSON) into a static SVG or HTML visualization.
  - User constraints include any of "static only", "no animation", "must be deterministic", "offline", or "diffable output" — D3 is the right tool to satisfy them.
  - Building an interactive (tooltips, hover-highlight, click-to-select) but still file-bytes-stable visualization.

do_not_use_when:
  - User only needs a quick table or text summary — produce a markdown table or spreadsheet instead.
  - The user explicitly requires a different chart library (Plotly, Vega, matplotlib) or a hosted/web-rendered chart with live data.
  - The output must update from a live data source at runtime — D3 here is used for static, reproducible artifacts.

scope_and_approval: >
  Read-only on the input data. Writes only under the caller-supplied
  output folder (default `dist/`) and vendors D3 into `vendor/`. The
  validation step (`scripts/check_determinism.py`) is mandatory and
  blocking — do NOT mark the visualization complete with any
  determinism `[error]` outstanding. Treat the determinism rules in
  `steps.validate-determinism` as gates, not suggestions.

steps:
  - name: gather-intent
    description: >
      Resolve the chart intent from the user request and the data
      files. Required: chart type (or inferred from data shape — bar
      for categorical+numeric, line/area for time-series, scatter for
      two numerics, histogram for one numeric, heatmap for two
      categoricals + numeric); x/y fields and aggregation rules;
      sort/filter rules; width/height and margins; color rule
      (categorical vs sequential); labels (title, axis labels, units);
      output constraints (`static only`, `no animation`, `offline`,
      `deterministic`). If any of these are missing, pick reasonable
      defaults AND record the defaults as a comment block near the top
      of `dist/chart.html` so the output is self-documenting.
    inputs:
      - name: data_files
        type: list[string]
        description: Paths to local `.csv`, `.tsv`, and/or `.json` inputs.
      - name: user_request
        type: string
        description: The user's stated chart goal and any constraints.
    outputs:
      - name: chart_spec
        type: object
        description: Resolved spec — chart type, encodings, dimensions, color rule, labels, output constraints, and an explicit list of defaults applied.

  - name: vendor-d3
    description: >
      Ensure a pinned local D3 build is available — default
      `vendor/d3.v7.9.0.min.js`. NEVER reference a CDN URL from the
      HTML. If the file is missing, copy from a known local mirror or
      ask the user to provide one; do not attempt a network fetch
      silently. The pinned version is the source of API truth for the
      rest of the steps.
    outputs:
      - name: d3_vendor_path
        type: string
        description: Relative path to the vendored D3 file (default `vendor/d3.v7.9.0.min.js`).

  - name: sort-and-format-data
    description: >
      Load each data file with the matching D3 loader (`d3.csv`,
      `d3.tsv`, `d3.json`). Coerce numeric columns explicitly (`+d.x`)
      and parse dates with an explicit `d3.timeParse` format —
      locale-default parsing is forbidden. Sort rows deterministically
      before binding (e.g., by x, then by category as tiebreaker). For
      groupings, materialize the key order with
      `Array.from(grouped.keys()).sort()` so iteration order is
      stable. Numeric formatting uses `d3.format` with an explicit
      pattern (e.g., `","`, `".2f"`); time formatting uses
      `d3.timeFormat` with an explicit format string.
    depends_on: [gather-intent]
    inputs:
      - name: chart_spec
        type: object
      - name: data_files
        type: list[string]
    outputs:
      - name: bound_data
        type: list[object]
        description: Sorted, type-coerced records ready to bind to D3 marks.

  - name: author-d3-render
    description: >
      Produce `dist/chart.html` — a single standalone file that loads
      the vendored D3 with a relative `<script src="../vendor/...">`
      tag, embeds CSS inline, and contains the rendering JS inline.
      Rendering rules — fixed `width`, `height`, `margin`, and
      `viewBox`; no transitions/animations by default; no random; if a
      force simulation is unavoidable seed the initial positions on a
      sorted grid, set a fixed tick count, and call `simulation.stop()`
      after exactly N ticks. Stable IDs only — derive from semantic
      strings (`"clip-plot"`, `"grad-revenue"`), never auto-generated
      counters. Round emitted numeric coordinates to 2–4 decimals.
      Write the output with LF line endings.
      Reference patterns: see `references/bubble_chart_example.js` for
      force layouts and `references/interactive_table_example.js` for
      sortable / linked-highlight tables.
    depends_on: [vendor-d3, sort-and-format-data]
    inputs:
      - name: chart_spec
        type: object
      - name: bound_data
        type: list[object]
      - name: d3_vendor_path
        type: string
    outputs:
      - name: html_path
        type: string
        description: Path to the written `dist/chart.html`.

  - name: add-interactivity-if-needed
    description: >
      Only when the spec asks for tooltips, hover-highlight, or
      click-to-select. Follow the CSS-class tooltip pattern (not
      `display:none`) — a `#tooltip` div with `opacity:0` by default
      and a `.visible` class toggled via `.classed('visible', true)`.
      Use `pointer-events: none` on the tooltip so it never blocks
      mouse events. Position with `event.pageX + 10` / `event.pageY -
      10`. For click-to-select, toggle a `.selected` class on the bound
      element. For conditional interactivity (e.g., suppress the
      tooltip for a category like `ETF`), return early from the
      `mouseover` handler; do NOT just hide the tooltip after
      population — that leaks content into the DOM. The reusable
      `TooltipHandler` class in `references/tooltip_handler.js` and
      the in-browser sanity check in `references/check_tooltip.js`
      cover both patterns. Anti-pattern: showing a tooltip for every
      data point when the spec says "only when complete data exists".
    depends_on: [author-d3-render]
    inputs:
      - name: chart_spec
        type: object
      - name: html_path
        type: string
    outputs:
      - name: html_path
        type: string
        description: Same `dist/chart.html`, with interactivity wired in.

  - name: export-outputs
    description: >
      Always write `dist/chart.html`. Additionally write
      `dist/chart.svg` whenever feasible — the SVG is what diffs/hashes
      stably between runs and is the primary determinism artifact.
      Write `dist/chart.png` ONLY when the task explicitly requires a
      raster. Stay in `dist/` unless the task specifies different
      paths. Use LF line endings on every text output.
    depends_on: [add-interactivity-if-needed]
    inputs:
      - name: html_path
        type: string
    outputs:
      - name: output_paths
        type: list[string]
        description: Absolute or repo-relative paths to all files written under `dist/`.

  - name: validate-determinism
    description: >
      Run the script on every text output written under `dist/`. Any
      `[error]` from the script blocks completion. Fix the underlying
      code and re-run until the script reports `OK`. Warnings (e.g., a
      lingering `.transition()` call) should be reviewed but do not
      block. The validator enforces the non-negotiable rule set — no
      `Math.random()`, no `d3.random*`, no CDN-loaded D3, no
      `Date.now()` / argless `new Date()`, fixed `viewBox` or explicit
      width+height, transitions are flagged.
    script: scripts/check_determinism.py
    depends_on: [export-outputs]
    inputs:
      - name: output_paths
        type: list[string]
    outputs:
      - name: determinism_report
        type: object
        description: Pass/fail plus per-file violation list. On any error, the procedure loops back to `author-d3-render`.

scenarios:
  - need: User supplies `stocks.csv` (ticker, sector, marketCap) and asks for "a sector bubble chart, deterministic, no animation".
    context: The data has a categorical (`sector`) and a numeric (`marketCap`); some rows have missing `marketCap`.
    action: gather-intent → bubble chart with `scaleSqrt` radius, categorical color by sector, fallback radius for missing values; vendor `d3.v7.9.0.min.js`; sort rows by sector then ticker; render with a seeded force simulation (300 ticks, sorted-grid initial positions, `simulation.stop()`); export HTML + SVG; run `check_determinism.py`.
    outcome: "`dist/chart.html`, `dist/chart.svg`, `vendor/d3.v7.9.0.min.js`. Re-running on the same data produces byte-identical SVG."
  - need: User asks for a hover-tooltip on the bubble chart, but tooltips should not appear for `ETF` rows.
    context: The existing chart already passes the determinism gate.
    action: add-interactivity-if-needed → `#tooltip` div with `opacity:0`/`.visible` toggle, `pointer-events:none`, conditional return-early in `mouseover` for `sector === 'ETF'`. Pattern lifted from `references/tooltip_handler.js`.
    outcome: Tooltips render on non-ETF bubbles; ETF bubbles show no tooltip and no leaked DOM content. Re-run of `check_determinism.py` still passes.
  - need: Task says "no D3 CDN, must work offline".
    context: The starter HTML loads D3 from `https://d3js.org/d3.v7.min.js`.
    action: vendor-d3 → copy `d3.v7.9.0.min.js` into `vendor/`, replace the `<script>` tag with a relative path. validate-determinism flags the original CDN reference and refuses to mark complete until it's removed.
    outcome: HTML loads D3 from `../vendor/d3.v7.9.0.min.js`; determinism script reports `OK`.

integrations:
  - partner: data-loading skills (CSV/TSV/JSON parsers)
    body: >
      `sort-and-format-data` expects already-decoded files at known
      local paths; pair this skill with whatever upstream produced
      them. The skill never assumes network access for data.
  - partner: rasterization tooling
    body: >
      `export-outputs` produces `dist/chart.png` only on explicit
      request. The conversion is delegated (e.g., headless Chromium,
      resvg) — pick a tool that itself produces deterministic raster
      output (fixed font fallback chain, fixed DPI). The PNG is NOT
      the determinism witness; the SVG is.

anti_patterns:
  - Loading D3 from a CDN. `<script src="https://d3js.org/...">` breaks the offline guarantee and the validator will reject it.
  - Using `Math.random()` or any `d3.random*` helper anywhere in the render path.
  - Default `.transition()` calls "for smoothness". They introduce timing variance and are flagged.
  - Auto-generated DOM/SVG IDs (e.g., D3-internal counters). Derive every ID from a stable semantic string (`"clip-plot"`, `"grad-revenue"`).
  - Locale-default number or date formatting. Always use `d3.format(...)` and `d3.timeFormat(...)` with explicit format strings.
  - Hardcoding `time_step`, output paths, or chart dimensions when the spec passes them in. Take them from the spec / config.
  - Showing a tooltip for every datum when the spec says it should be conditional (e.g., "no tooltip for ETFs"). Use an early `return` in the `mouseover` handler — do not show-then-hide.
  - "Toggling tooltip visibility with `display: none`. Use the `.visible` CSS class and `opacity` so positioning, transitions, and pointer-events stay consistent."
  - Letting a force simulation run to natural rest. Always seed initial positions deterministically, fix tick count, and call `simulation.stop()`.
  - Skipping `scripts/check_determinism.py` before reporting the chart "done". The validator is the contract.
```
