# D3.js patterns and determinism rules

Load this file when you edit the generated `js/visualization.js` (the scope =
`extended` branch), or when the task wants a chart the template does not draw.
It carries the general rules from the source `d3-visualization` skill.

## Inputs to expect, defaults to choose

- Local data files: `*.csv`, `*.tsv`, `*.json`.
- Chart intent: chart type (or infer it), x/y fields and aggregation, sorting
  and filtering, width/height and margins, color rules (categorical or
  sequential), labels (title, axis labels, units).
- Output constraints: "static only", "no animation", "deterministic", "offline".
- If details are missing, choose reasonable defaults and document them in a
  comment at the top of the output file (the template's header comment does this).

## Outputs when the task names no paths

- `dist/chart.html` (standalone HTML rendering the chart), `dist/chart.svg`
  (exported, diff-friendly), `dist/chart.png` only if a raster is explicitly
  needed. Vendor D3 under `vendor/` (e.g. `vendor/d3.v6.7.0.min.js`).
- When the task names paths (this skill's task does: `/root/output/...`), use
  exactly those.

## Determinism rules

Data
- Sort rows deterministically before binding (e.g. by sector, then value, then
  ticker). Use a stable group order: `Array.from(groups.keys()).sort()`.
- Format numbers and dates with explicit formats (`d3.format`, `d3.timeFormat`,
  or a fixed formatter such as `formatMarketCap`), not the locale.

Rendering
- No randomness: no `Math.random()`, no `d3-random`.
- No transitions or animations by default (timing variance). A short CSS
  opacity transition on the tooltip is fine.
- Fixed `width`, `height`, margins and `viewBox`.
- Explicit tick counts only when needed; keep scale domains fixed.
- Force layouts: set initial positions deterministically (the template uses a
  sunflower spiral around each sector anchor), run a fixed number of ticks
  synchronously (`simulation.stop()` then `tick()` N times), and stop.

Offline and dependencies
- Never load D3 from a CDN at runtime. Vendor a pinned minified bundle. The
  source skill's default pin was d3@7.9.0; the task's requested version
  overrides it (this skill vendors d3@6.7.0 as `assets/d3.v6.min.js`).

Files
- Avoid auto-generated IDs. Derive any IDs (clipPath, gradients, elements)
  from stable strings, e.g. `"clip-plot"`, `bubble-<ticker>`.
- LF line endings. Consistent numeric precision (round coordinates to 2-4 decimals).

## Tooltip pattern

```html
<div id="tooltip" class="tooltip"></div>
```
```css
.tooltip { position: absolute; padding: 10px; background: rgba(0,0,0,0.8);
  color: white; border-radius: 4px; pointer-events: none; opacity: 0;
  transition: opacity 0.2s; z-index: 1000; }
.tooltip.visible { opacity: 1; }
```
```javascript
selection
  .on('mouseover', function (event, d) {          // D3 v6: (event, d)
      if (!d.hasTooltip) return hideTooltip();     // conditional: e.g. no ETFs
      d3.select('#tooltip').classed('visible', true)
        .html(`<strong>${d.ticker}</strong><br/>${d.name}<br/>Sector: ${d.sector}`)
        .style('left', (event.pageX + 10) + 'px')
        .style('top', (event.pageY - 10) + 'px');
  })
  .on('mousemove', moveTooltip)
  .on('mouseout', () => d3.select('#tooltip').classed('visible', false));
```
- Hide with `opacity: 0` (not `display: none`) and toggle the `.visible` class.
- `pointer-events: none` on the tooltip so it never blocks mouse events.
- Position from `event.pageX` / `event.pageY`.
- Exit early in the handler for elements that must not get a tooltip.
- Escape data before putting it in `.html()` (names contain `&`).

## Click selection and highlighting

```javascript
.on('click', (event, d) => select(d.ticker));
function select(ticker) {
  d3.selectAll('.bubble').classed('selected', d => d.ticker === ticker);
  d3.selectAll('#stock-table tbody tr').classed('selected', d => d.ticker === ticker);
}
```
```css
.bubble.selected { stroke: #000; stroke-width: 3px; }
tr.selected { background: #e3f2fd; }
```
- One function updates both views, so chart -> table and table -> chart
  stay consistent. Key table rows by ticker: `.data(rows, d => d.ticker)`.
- Sortable headers re-render the rows; recompute `selected` from state on
  every render so the highlight survives sorting.

## Number format for market cap

`>= 1e12 -> x.xxT`, `>= 1e9 -> x.xxB`, `>= 1e6 -> x.xxM`, `>= 1e3 -> x.xxK`,
else two decimals; missing -> `-`. Example: 1641026945024 -> `1.64T`.
Implemented as `formatMarketCap` (JS) and `format_cap` (Python, used by the
verifier); change both together.

## Self-check in the browser console

Ported from the source `check_tooltip.js`: confirm `#tooltip` exists, check
its computed opacity before and after adding `.visible`, and check that its
HTML holds ticker, name and sector. `scripts/verify_app.py` automates all of
this by hovering every bubble.
