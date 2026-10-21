# Provenance

Compiled into `d3-stock-bubble-table` from one curated skill:

- `source/d3-visualization/SKILL.md` (frontmatter name `d3js-visualization`): general rules for deterministic, offline D3 output, plus the tooltip, click and conditional-interactivity patterns.
- `source/d3-visualization/scripts/bubble_chart_example.js`: bubble chart with force simulation and sector clusters.
- `source/d3-visualization/scripts/interactive_table_example.js`: sortable table with linked highlighting and the T/B/M/K formatter.
- `source/d3-visualization/scripts/tooltip_handler.js`: reusable tooltip class with a conditional `shouldShow`.
- `source/d3-visualization/scripts/check_tooltip.js`: browser-console tooltip checks.

All originals are copied here verbatim. The target task is `inputs/instruction.md` of the authoring run. It asks for a D3 v6 single-page app at `/root/output` from `/root/data/stock-descriptions.csv` plus `/root/data/indiv-stock/*.csv`, with a bubble chart and a linked table. The container is Ubuntu 24.04 with python3, Node/npm, and pip `playwright` with Chromium.

`assets/d3.v6.min.js` is d3@6.7.0 (`https://cdn.jsdelivr.net/npm/d3@6.7.0/dist/d3.min.js`). It is vendored so the build needs no network, and `assets/D3-LICENSE.txt` is its ISC license.

# Intent

The source was a generic D3 skill whose examples sketched this exact task, using stocks, ETFs, sectors, a tooltip with no ETFs, and a linked table. The distilled skill turns those sketches into one tested generator (`build_app.py` plus templates) and a verifier (`verify_app.py`). Its general D3 knowledge is kept in `references/d3-patterns.md` for when the task goes beyond the template.

# Component kinds

| Component | Kind | Why |
|---|---|---|
| Prerequisite check | execution (shell one-liners in the body) | Deterministic presence test. |
| Inspect data (`build_app.py inspect`) | execution | Column mapping, ETF rule, sector counts, price-file matching and number formatting are all deterministic rules over the CSV. |
| Judge inspection: `mapping_correct`, `etf_rule_correct`, `scope` | decision (2 noul + 1 choice) | A column's meaning, and whether the task wants more than the template, need judgment, but the answer space is fixed. Each answer maps to a concrete action (`--col`, `--etf-sector`, step 5 or not). |
| Build app (`build_app.py build`) | execution | Writing the files, copying data, vendoring D3, embedding config and rows: no judgment involved. The chart logic is in a tested template rather than regenerated each run, because a hand-written force layout is the main source of overlap, scatter and centering failures. |
| Extend app (scope = extended) | client_task | Requests beyond the template (price charts, other columns) are code the agent must write. |
| Verify (`verify_app.py`) | execution | Every requirement in the task can be checked mechanically in headless Chromium against the CSV: file layout, D3 v6, bubble count, labels, overlap, bounds, centering, size order, uniform ETF size, colors, clusters, legend, side-by-side layout, table headers and contents, tooltips on every bubble, and linked clicks in both directions. It runs over file:// and http. |
| Report | client_task | Free-text summary. |

Two scripts, not more: inspect and build share mapping and format code, and the verifier imports them so expectations and implementation cannot drift.

# Adaptations (source -> skill)

- Radius: the source used `scaleSqrt().range([5, 50])` with radius 10 for missing values. The skill solves the largest radius so bubbles cover about 42% of the viewBox, with a minimum radius of 14 and ETF radius = max(14, 0.3 x largest). A fixed [5, 50] either overflows or leaves the chart empty depending on the row count, and 5 px cannot hold a ticker label.
- Clustering: the source used `forceCenter` + `forceManyBody(-30)` + forceX/forceY(0.5) toward points on a fixed 150 px ring. The skill uses forceX/forceY(0.12) toward anchors packed with `d3.packSiblings` from each sector's total area, plus forceCollide(r + 1.5) with 3 iterations. Charge pushes clusters apart and the fixed ring ignores cluster size, which cause the "scattered far away" and overlap failures the task forbids. The source's own determinism rules (fixed ticks, deterministic starts, stop) are applied, where the example animated on `tick`.
- Data path: the source used `d3.csv('/data/stocks.csv')`. The skill uses a relative `data/<file>` with an embedded-rows fallback, because an absolute path and `file://` fetch both fail when the page is opened directly.
- Table: the source had labels Ticker / Company Name / Sector / Market Cap with styles injected from JS. The skill uses the task's exact labels and puts the styles in `css/style.css`, which the task requires. Sortable headers, the key function and formatNumber are kept.
- Tooltip: the `TooltipHandler` class became plain functions (`showTooltip`, `moveTooltip`, `hideTooltip`) with the same behavior: conditional `shouldShow` (`hasTooltip`), the `.visible` class, `pointer-events: none`, pageX/pageY offsets, and following the mouse. HTML escaping was added because names contain `&`.
- Highlight: the source split it into `selected` on rows (selectRow) and `highlighted` (highlightTableRow). The skill sets both classes on both views from one `select()` so either check passes.
- D3 version: the source pinned d3@7.9.0, but the task requires v6, so 6.7.0 is vendored. The rule "the task's version wins" is written into the body.

# Deliberate drops

| Source item | Why dropped |
|---|---|
| Trigger list of other chart types (bar/line/scatter/area/histogram/box/violin/heatmap, timelines, small multiples, faceting) | The skill is scoped to the bubble + table task family. The general D3 rules that apply to those charts are kept in `references/d3-patterns.md`, and `scope: other` routes to it. |
| Default outputs `dist/chart.svg` and `dist/chart.png` | The task names its outputs (`/root/output/...`) and wants an interactive page, not an exported SVG/PNG. The default layout is documented in the reference for tasks with no paths. |
| "Use explicit tick counts only when needed" (axes) | This chart has no axes. The rule is kept in the reference. |
| `tooltip_handler.js` example 4 (multiple tooltips with separate selectors) and `.tooltip-header`/`.tooltip-body` rich-format CSS | No tooltip beyond the bubbles is required. The single-tooltip pattern covers what is needed. |
| `tooltip_handler.js` example 3 (market cap line in the tooltip) | The task specifies the tooltip as ticker, name and sector. Adding fields is a step 5 extension. |
| `module.exports` in `tooltip_handler.js`; JS-injected `<style>` in `interactive_table_example.js` | Browser-only page with a required css/style.css file. |
| `check_tooltip.js` console logging of computed styles | Superseded by `verify_app.py`, which checks opacity and contents by hovering every bubble. The manual procedure is summarized in the reference. |
| Bubble `opacity 0.7` | Changed to 0.85 for readable white labels. Cosmetic. |
