# Map of the generated app (what `build_app.py` writes)

```
<output_dir>/
  index.html            header, main#dashboard.dashboard > section#chart-panel (div#chart)
                        + section#table-panel (div#table-container); div#tooltip.tooltip;
                        scripts: js/d3.v6.min.js then js/visualization.js
  css/style.css         flex row layout, .bubble/.bubble-label, .legend-item, .tooltip(.visible),
                        #data-table (sticky header, tr.selected highlight)
  js/d3.v6.min.js       vendored D3 v6.7.0 (assets/vendor), never a CDN
  js/visualization.js   assets/app/visualization.js with CONFIG + EMBEDDED_ROWS filled in
  data/                 verbatim copy of the input data folder (same sub-folders)
```

## visualization.js (one IIFE)

| Piece | What it does |
|---|---|
| `CONFIG` | `dataPath` (`data/<descriptions csv>`), `columns` (logical -> CSV header: ticker, name, sector, marketCap, country, website), `width`/`height` of the SVG (700x620), `palette`, `priceFiles` (UPPER-CASE ticker -> `data/<price dir>/<file>.csv`, only tickers that have a file) |
| `PRICE_FILES` | alias of `CONFIG.priceFiles`; unused by the default app, ready for a price panel |
| `EMBEDDED_ROWS` | the descriptions rows (mapped columns only); used when `d3.csv(CONFIG.dataPath)` fails, e.g. file:// |
| `normalize(raw)` | CSV rows -> `{ticker, name, sector, marketCap, country, website, isETF}`; `isETF` = sector "ETF" or no positive market cap |
| `sectorOrder`, `sortRows` | sectors alphabetical, no-market-cap groups last; rows by sector then ticker (deterministic binding) |
| `formatMarketCap` | `1.64T` / `193.22B` / `850.00M`; missing -> `N/A` |
| `selectTicker(t, scrollRow)` | sets class `selected` on `circle.bubble` and `#data-table tbody tr` whose datum ticker is `t`; scrolls the row into view on bubble click. Also exposed as `window.highlightTableRow` / `window.highlightBubble` |
| `showTooltip/moveTooltip/hideTooltip` | toggles `.visible` on `#tooltip`; returns early for `isETF` rows; content = ticker, name, "Sector: ..." |
| `drawLegend` | `g.legend > g.legend-item[data-sector]` (circle + text) in a band at the top of the SVG; returns the band's bottom y |
| `layout(nodes, sectors, area)` | radii (scaleSqrt of market cap, floor so labels fit; ETFs = median radius), sector anchors = one circle per sector (radius from its bubbles' total area at ~62% density + gap) packed with `d3.packSiblings` and centred, forceX/forceY(0.2) to anchors + forceCollide(r+1.5, 4 iterations), 400 fixed ticks + 60 collide-only ticks, shrink-and-retry until the bounding box fits, then re-centre |
| `drawBubbles` | `svg#bubble-chart` (fixed width/height/viewBox) > `g.bubbles > g.node[transform]` each with `circle.bubble[data-ticker][data-sector]` (+ `.etf`) and `text.bubble-label` (pointer-events none) |
| `drawTable` | `table#data-table`, headers exactly "Ticker symbol", "Full company name", "Sector", "Market cap"; `tr[data-ticker]` rows, click -> `selectTicker` |
| `render` | normalize -> order -> bubbles -> table, then sets `body[data-rendered=true]` (the verifier waits on it) |

## Adding a panel (custom branch)

- Add a `<section class="panel">` inside `main#dashboard` only if the task allows a third
  item in the row; otherwise put it below the dashboard so the two required charts stay
  side by side.
- For a price panel: look the file up in `PRICE_FILES[ticker.toUpperCase()]`, load it with `d3.csv`, and show a clear message when there is no entry or the fetch fails (file://).
- Hook new behaviour into `selectTicker` (e.g. redraw a price line for the selected ticker)
  rather than adding a second selection mechanism.
- Keep `render` setting `data-rendered` last, after every panel is drawn.
- If you widen the chart, adjust `CONFIG.width` in the generated file and the table's
  `min-width` in style.css together; the verifier uses a 1500px-wide viewport.
