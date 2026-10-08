# D3 visualization rules and patterns

Load when hand-writing or editing D3 code (custom charts, requirement fixes, verifier failures).

## Inputs to expect
- Local data files: `*.csv`, `*.tsv`, `*.json`.
- A chart intent: chart type (or infer the best one), x/y fields and aggregation, sorting/filtering, width/height/margins, color rules (categorical/sequential), labels (title, axis labels, units).
- Output constraints such as "static only", "no animation", "deterministic", "offline".
- Missing details: choose reasonable defaults and document them in a comment block at the top of the output file.

## Outputs
Unless the task fixes paths, produce all of:
1. `dist/chart.html`: standalone HTML that renders the chart.
2. `dist/chart.svg`: exported SVG (stable, diff-friendly).
3. `dist/chart.png`: only if a raster image is explicitly needed.
(`dist/` = the output_dir; when the task names no folder, `dist/` under the current working directory.)

Default layout:
```
dist/
  chart.html        # standalone HTML with inline or linked JS/CSS
  chart.svg         # exported SVG (optional but nice)
  chart.png         # rasterized (optional)
  vendor/
    d3.v6.7.0.min.js  # pinned D3 library
```
Keep outputs in a predictable folder (default `dist/`). The original guidance puts `vendor/` beside `dist/`;
this skill nests it inside so the folder is self-contained (either serves fine; the verifier serves the
common parent of all referenced files).

## Determinism (non-negotiable)
Data
- Sort rows deterministically before binding to marks (by x, then category).
- Stable grouping order: `Array.from(grouped.keys()).sort()`.
- No locale-dependent formatting unless fixed: `d3.format`, `d3.timeFormat`/`d3.utcFormat` with explicit formats.

Rendering
- No `Math.random()`, no `d3-random`.
- No transitions/animations by default (timing variance).
- Fixed `width`, `height`, `margin`, `viewBox`.
- Explicit tick counts only when needed; otherwise D3 defaults, but keep domains fixed.
- Layouts with non-deterministic iteration (force simulation): fix initial positions deterministically (sorted nodes on a grid/spiral), fix the tick count, run exactly N ticks and stop (`simulation.stop(); for (i < N) simulation.tick();`).

Offline + dependencies
- Never load D3 from a CDN. Pin a version and vendor the minified bundle locally (`scripts/vendor_d3.py`; bundled copies: 6.7.0 and 7.9.0). Use the version the task names. When it names none, use 6 (bundled 6.7.0), matching the source skill's "D3.js (v6)" description; its body suggested d3@7.9.0, which is also bundled and has the same API for these charts.
- Load the D3 `<script>` before any script that uses `d3`.

Files
- No auto-generated IDs that may change; derive needed IDs (clipPath, gradients) from stable strings (`"clip-plot"`).
- LF line endings. Consistent numeric precision (round to 2–4 decimals).

## Tooltip pattern
```html
<div id="tooltip" class="tooltip"></div>
```
```css
.tooltip { position: absolute; padding: 10px; background: rgba(0,0,0,0.8); color: white;
  border-radius: 4px; pointer-events: none; opacity: 0; z-index: 1000; }
.tooltip.visible { opacity: 1; }
```
```javascript
svg.selectAll('circle')
  .on('mouseover', function (event, d) {
    d3.select('#tooltip').classed('visible', true)
      .html(`<strong>${d.name}</strong><br/>${d.value}`)
      .style('left', (event.pageX + 10) + 'px')
      .style('top', (event.pageY - 10) + 'px');
  })
  .on('mouseout', function () { d3.select('#tooltip').classed('visible', false); });
```
- Hide with `opacity: 0` (not `display: none`); toggle with `.classed('visible', true/false)`.
- `pointer-events: none` so the tooltip never blocks mouse events; same for text labels drawn over marks.
- Position from `event.pageX/pageY` (D3 v6+ passes `(event, d)` to listeners; `d3.event` no longer exists).
- The original guidance adds `transition: opacity 0.2s`; this skill drops it so the visible state is immediate (determinism rule: no transitions).

Conditional interactivity — only some elements get a tooltip:
```javascript
.on('mouseover', function (event, d) {
  if (d.category === 'excluded') return;   // e.g. ETFs with no market-cap data
  showTooltip(event, d);
})
```

## Click selection / highlighting
```javascript
svg.selectAll('.bar').on('click', function (event, d) {
  d3.selectAll('.bar').classed('selected', false);
  d3.select(this).classed('selected', true);
});
```
```css
.bar.selected { stroke: #000; stroke-width: 3px; }
```
Linked views: one `selectKey(key)` updates every view (chart marks and table rows matched by a `data-key` attribute), clearing the previous selection.

## Linked table
- Key function on rows (`.data(rows, d => d.key)`) for stable updates; header click sorts (strings `localeCompare`, numbers numeric, missing last), toggling ascending/descending.
- Number formatting for large values: 2 decimals + suffix (`1.64T`, `512.30B`, `3.20M`, `4.50K`); empty → "-".
- Row styles: `tr:hover`, `tr.selected` (blue background + left border), `tr.highlighted` (yellow).

## Bubble charts
- `d3.scaleSqrt().domain([0, max]).range([5, 50])` so area tracks value; rows without a value get a uniform radius (10).
- `d3.scaleOrdinal(d3.schemeCategory10)` over the sorted category domain.
- Cluster by category: `forceX/forceY` toward per-category centres on a ring, `forceCollide(r + 2)`, `forceManyBody(-30)`.
- Worked examples: `references/examples/bubble_chart_example.js`, `interactive_table_example.js`, `tooltip_handler.js` (reusable TooltipHandler with `shouldShow`), `check_tooltip.js` (console checks for the tooltip element and `.visible`). They animate the force simulation with `on('tick')` and an `opacity` transition; in generated pages replace that with a fixed tick loop and no transition.

## Do not use D3 when
The user only needs a quick table or summary: use a spreadsheet or plain markdown.
