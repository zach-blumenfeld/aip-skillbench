# D3.js patterns for deterministic, verifiable visualizations

Adapted from the source `d3-visualization` skill (source/d3-visualization/). Load when
editing or repairing chart code. The task's D3 version wins over the source's default
(source default: d3@7.9.0; this task: v6, vendored as `js/d3.v6.min.js`).

## Inputs and outputs

- Expect local `*.csv` / `*.tsv` / `*.json` plus a chart intent: chart type (or infer),
  x/y fields and aggregation, sort/filter rules, width/height/margins, color rules
  (categorical/sequential), labels (title, axes, units), output constraints (static,
  no animation, deterministic, offline).
- Missing details: pick reasonable defaults and document them in a comment near the top
  of the output file.
- Outputs go where the task says. Without a task layout use `dist/chart.html`
  (+ optional `dist/chart.svg`, `dist/chart.png` only if a raster is asked for) and
  `vendor/d3.<version>.min.js`.
- If the user only needs a quick table or summary, do not use D3.

## Determinism rules (non-negotiable)

Data
- Sort rows deterministically before binding (e.g. by category then key).
- Stable group order: `Array.from(grouped.keys()).sort()`.
- No locale-dependent formatting; use `d3.format` / `d3.timeFormat` with explicit formats.

Rendering
- No randomness: no `Math.random()`, no `d3-random`.
- No transitions/animations by default.
- Fixed `width`, `height`, `margin`, `viewBox`.
- Explicit tick counts only when needed; keep domains fixed.
- Force layouts: fix initial positions deterministically (sorted nodes on a grid/spiral),
  call `.stop()`, run exactly N `tick()`s, then draw.

Offline + dependencies
- Never load D3 from a CDN; pin and vendor the minified bundle.

Files
- Avoid auto-generated IDs; derive needed IDs (clipPath, gradients) from stable strings
  (`"clip-plot"`). LF line endings. Consistent numeric precision (2-4 decimals).

## Tooltip pattern

```html
<div id="tooltip" class="tooltip"></div>
```
```css
.tooltip { position: absolute; padding: 10px; background: rgba(0,0,0,0.8); color: white;
  border-radius: 4px; pointer-events: none; opacity: 0; transition: opacity 0.2s; z-index: 1000; }
.tooltip.visible { opacity: 1; }
```
```javascript
svg.selectAll('circle')
  .on('mouseover', function (event, d) {
    if (d.category === 'excluded') return;          // conditional: no tooltip for some rows
    d3.select('#tooltip').classed('visible', true)
      .html(`<strong>${d.ticker}</strong><br/>${d.name}<br/>Sector: ${d.sector}`)
      .style('left', (event.pageX + 10) + 'px')
      .style('top', (event.pageY - 10) + 'px');
  })
  .on('mousemove', (event) => { /* follow the mouse while visible */ })
  .on('mouseout', () => d3.select('#tooltip').classed('visible', false));
```
- Hide with `opacity: 0`, not `display: none`; toggle with `.classed('visible', ...)`.
- `pointer-events: none` on the tooltip (and on labels drawn over marks) so it never
  steals the mouse.
- Position from `event.pageX/pageY` (D3 v6 passes `(event, d)` to listeners).
- Reusable form: a handler with `shouldShow(d)` and `formatContent(d)` options and
  `attach(selection)` wiring mouseover/mousemove/mouseout
  (source/d3-visualization/scripts/tooltip_handler.js).

## Click selection and chart <-> table linking

```javascript
.on('click', function (event, d) {
  d3.selectAll('.bubble').classed('selected', x => x.ticker === d.ticker);
  d3.selectAll('#data-table tbody tr').classed('selected', x => x && x.ticker === d.ticker);
});
```
```css
.bubble.selected { stroke: #000; stroke-width: 3px; }
tr.selected { background: #e3f2fd !important; border-left: 3px solid #2196f3; }
```
- Bind table rows with a key function (`.data(rows, d => d.ticker)`) so updates and
  re-sorts keep identity; one shared select function drives both directions.
- Optional column sorting: click a `th` to toggle ascending/descending; compare strings
  with `localeCompare`, numbers with missing treated as 0, then re-render rows
  (source/d3-visualization/scripts/interactive_table_example.js).

## Bubble chart with force clustering (source example, corrected)

- `d3.scaleSqrt()` for radius so area tracks value; rows with no value get one uniform
  radius and are flagged (`hasValue = false`).
- `d3.scaleOrdinal().domain(sectors).range(d3.schemeCategory10)` (or a fixed palette).
- Cluster anchors per category (source: on a circle of radius 150 around the centre; the
  built app packs one circle per category, sized from its total bubble area, with
  `d3.packSiblings` so unequal clusters neither mix nor leave a hollow centre);
  `forceX/forceY(anchor).strength(~0.2-0.5)`, `forceCollide(r + 2)`; the source also adds
  `forceCenter` and `forceManyBody(-30)`, which fight the clustering at this size, so the
  built app omits them.
- The source updates positions in `simulation.on('tick')`; for determinism stop the
  simulation and tick a fixed count instead.

## Number formatting

`1.64T`, `193.22B`, `850.00M`, `12.30K` via `(n / 1e12).toFixed(2) + 'T'` etc.; keep the
sign for negatives; missing -> a placeholder (`-` in the source scripts, `N/A` in the app).
`d3.format('.3s')` is not a substitute: it prints `G` for billions.

## Verifying tooltips in a browser

Check that `#tooltip` exists, that it gains the `visible` class and non-zero computed
opacity on hover of an eligible mark, that its text contains the expected fields, and that
it stays hidden for excluded marks (source/d3-visualization/scripts/check_tooltip.js;
automated in scripts/verify_app.py).
