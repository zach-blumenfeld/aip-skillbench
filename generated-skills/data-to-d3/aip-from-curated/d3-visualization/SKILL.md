---
name: d3js-visualization
description: Build deterministic, verifiable data visualizations with D3.js (v6). Generate standalone HTML/SVG (and optional PNG) from local data files without external network dependencies. Use when tasks require charts, plots, axes/scales, legends, tooltips, or data-driven SVG output.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Turn structured local data (CSV/TSV/JSON) into clean, reproducible D3.js
  visualizations whose outputs are stable across runs and machines. Produce
  standalone HTML and SVG (optionally PNG) that can be verified by file diff
  or hash. Enforce determinism — no randomness, no transitions, fixed
  dimensions, pinned offline D3, stable element IDs — and document any
  defaults inferred from underspecified intent in a header comment on the
  output file.

trigger_when:
  - User asks to make a chart, plot, graph, or visualization.
  - Task names a chart family — bar, line, scatter, area, histogram, box, violin, heatmap.
  - Task involves timelines, small multiples, or faceting.
  - Task requires axis ticks, scales, legends, or tooltips.
  - Task requires data-driven SVG output for a report or web page.
  - Task asks to convert one or more local data files into a static SVG or HTML visualization.

do_not_use_when:
  - User only needs a quick table or text summary — a spreadsheet or plain markdown is the better tool.
  - Task requires animation, transitions, or randomized interactive simulation as a first-class part of the deliverable (determinism rules disallow them).

scope_and_approval: >
  Writes new files under `dist/` (outputs) and `vendor/` (pinned D3) in the
  working directory. Never fetches from the network at render time — D3 is
  vendored locally. If existing files in those paths would be clobbered, ask
  the user before overwriting. When chart intent is underspecified, choose
  reasonable defaults and record them as a comment block at the top of
  `dist/chart.html` rather than blocking on confirmation.

steps:
  - name: gather-intent
    description: >
      Inventory the data files (CSV/TSV/JSON), then resolve the chart intent —
      chart type (infer the best fit if unspecified), x/y fields, aggregation
      and filtering rules, dimensions (width / height / margins), color rules
      (categorical vs sequential), labels (title, axis labels, units), and
      output constraints (static-only, offline, deterministic). Fill any gap
      with a sensible default and note it so it can be surfaced in the
      output file's header comment.
    outputs:
      - name: chart-spec
        type: object
        description: Resolved chart intent — type, fields, encodings, dimensions, labels, constraints, applied defaults.

  - name: prepare-layout-and-vendor-d3
    description: >
      Create the predictable output layout — `dist/` for outputs, `vendor/`
      for the pinned D3 library. Vendor D3 locally (default
      `vendor/d3.v7.9.0.min.js`); do not load D3 from a CDN, and do not fetch
      from the network at render time. If the task specifies an existing
      structure, use that instead.
    inputs:
      - name: chart-spec
        type: object
    outputs:
      - name: layout
        type: object
        description: Paths for `dist/chart.html`, `dist/chart.svg`, optional `dist/chart.png`, and the vendored D3 file.

  - name: load-and-sort-data
    description: >
      Load each data file with D3's loaders (`d3.csv`, `d3.tsv`, `d3.json`).
      Parse types explicitly — numbers via `+`, dates via `d3.timeParse` with
      a fixed format. Sort rows deterministically before binding (e.g., by x
      then by category). For grouped data, derive an explicit stable key
      order via `Array.from(grouped.keys()).sort()`. Never rely on engine
      iteration order or locale-default collation.
    inputs:
      - name: chart-spec
        type: object
    outputs:
      - name: sorted-data
        type: list[object]

  - name: design-scales-and-encodings
    description: >
      Pick scale types (linear, time, band, ordinal, sqrt) and color schemes
      appropriate to the data and chart. Fix domains explicitly so range and
      extent do not shift between runs. Use `d3.format` and `d3.timeFormat`
      with explicit format strings — avoid locale-dependent number/date
      formatting. Set explicit tick counts only when D3's default produces
      unstable output; otherwise rely on defaults with fixed domains. Keep
      numeric precision consistent (round to 2–4 decimals where output
      stability matters).
    inputs:
      - name: chart-spec
        type: object
      - name: sorted-data
        type: list[object]
    outputs:
      - name: encoding-plan
        type: object
        description: Scale types, fixed domains/ranges, color rules, axis tick policy, label/title strings, formatters.

  - name: render-chart
    description: >
      Emit standalone HTML at `dist/chart.html` (inline or linked JS/CSS) that
      renders the chart. Apply the determinism rules without exception —
      no `Math.random()` or `d3-random`; no transitions or animations by
      default; fixed `width`, `height`, `margin`, and `viewBox`; stable
      element IDs derived from fixed strings (e.g., `"clip-plot"`) for any
      clipPath, gradient, or filter; LF line endings throughout. If a
      force-directed layout is genuinely required, seed initial positions
      deterministically (e.g., sorted nodes on a grid), run exactly N ticks,
      then stop — treat random seeds as unavailable.
    inputs:
      - name: layout
        type: object
      - name: sorted-data
        type: list[object]
      - name: encoding-plan
        type: object
    outputs:
      - name: html-path
        type: string

  - name: add-interactivity
    description: >
      Add interactivity only when the task asks for it. Tooltip pattern —
      single `#tooltip` div, CSS-class-based visibility (toggle a `.visible`
      class that flips `opacity`), `pointer-events: none`, positioning via
      `event.pageX/pageY`. Click selection — toggle a `.selected` class on
      the clicked mark after clearing it from siblings. Conditional
      tooltips — early-return from the `mouseover` handler when the data
      point should be excluded. Full CSS and JS snippets live in
      `references/interactivity.md`; copy-ready reference implementations
      live in `scripts/tooltip_handler.js`,
      `scripts/bubble_chart_example.js`, and
      `scripts/interactive_table_example.js`. After wiring, mirror the
      sanity checks in `scripts/check_tooltip.js` (element exists,
      `.visible` toggles, content matches data).
    inputs:
      - name: chart-spec
        type: object
      - name: html-path
        type: string
    outputs:
      - name: html-path
        type: string

  - name: export-svg
    description: >
      Save the rendered SVG to `dist/chart.svg` as a stable, diff-friendly
      file. Avoid auto-generated IDs and locale-dependent formatting.
      Produce `dist/chart.png` only when the task explicitly asks for a
      raster image.
    inputs:
      - name: layout
        type: object
      - name: html-path
        type: string
    outputs:
      - name: svg-path
        type: string
      - name: png-path
        type: string
        nullable: true

  - name: verify-determinism
    description: >
      Re-render and diff or hash the outputs against a previous run — same
      input must produce byte-identical (or hash-identical) SVG and HTML.
      Audit the output for `Math.random`/`d3-random` calls, transitions,
      CDN URLs, auto-generated IDs, missing `viewBox`, CRLF line endings,
      and floating-precision drift. If outputs differ between runs, treat
      the drift as a defect — trace it to the offending step and fix it
      before reporting completion.
    inputs:
      - name: svg-path
        type: string
      - name: html-path
        type: string
    outputs:
      - name: verified
        type: boolean

anti_patterns:
  - Loading D3 from a CDN. Vendor a pinned local copy (default `d3@7.9.0`) under `vendor/`.
  - Using `Math.random()` or `d3-random` anywhere in the render path.
  - Adding transitions or animations by default — they introduce timing variance.
  - Relying on auto-generated element IDs for clipPaths, gradients, or filters; derive IDs from fixed strings.
  - Letting engine iteration order decide group or key ordering — sort explicitly.
  - Using locale-dependent number or date formatting without a fixed format string.
  - Running a force simulation without a fixed tick count and deterministic initial positions.
  - "Hiding tooltips with `display: none` — use `opacity: 0` plus a `.visible` class so transitions stay smooth and `pointer-events: none` keeps the mouse free."
  - Writing outputs outside the predictable folder (default `dist/`) so downstream diffs cannot find them.
  - Building a chart when the user only needs a table or a text summary.
```
