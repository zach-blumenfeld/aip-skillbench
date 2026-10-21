# Source and provenance: d3-bubble-table-app

## Provenance

- `d3-visualization/` — verbatim copy of the curated Agent Skill `d3js-visualization`
  (`SKILL.md` + `scripts/bubble_chart_example.js`, `scripts/interactive_table_example.js`,
  `scripts/tooltip_handler.js`, `scripts/check_tooltip.js`). It is the only curated skill
  for this workflow.
- Task context used to specialise it (not copied, not shipped): the task statement (D3 v6
  single-page app at `/root/output/index.html` with `js/d3.v6.min.js`, `js/visualization.js`,
  `css/style.css`, `data/` copy; bubble chart + linked table) and the real input files
  (`stock-descriptions.csv`: 50 rows, columns `,ticker,sector,full name,marketCap,...,country,website,...`,
  10 ETFs with empty marketCap/country/website; `indiv-stock/*.csv`: 40 stock files
  `,Date,Low,Open,Volume,High,Close,Adjusted Close` and 10 lower-case ETF files
  `,Date,Open,High,Low,Close,Volume,OpenInt`), and the container Dockerfile (Ubuntu 24.04,
  python3 3.12, pip `playwright` + Chromium, node/npm, curl; no D3 installed).
- `assets/vendor/d3.v6.min.js` — D3 v6.7.0 bundle (`cdn.jsdelivr.net/npm/d3@6.7.0/dist/d3.min.js`),
  ISC/BSD-style license in `assets/vendor/D3-LICENSE.txt`. Vendored so the build works offline.

## Intent

The source skill is a generic "deterministic D3 chart" guide whose examples are exactly
this task's pieces (clustered bubble chart, linked table, conditional ETF tooltip,
T/B/M formatting). The compiled skill turns those examples into one tested generator
plus a browser verifier, so an agent produces the full app in two script calls and
only reasons where the task departs from the default.

## Component-kind choices

| Step | Kind | Why |
|---|---|---|
| `build-app` | execution (`scripts/build_app.py`) | Column mapping, ETF detection, file layout, D3 vendoring, data copy and templating are deterministic. The chart logic itself is a fixed, tested JS template (`assets/app/visualization.js`) with config + embedded rows injected. |
| `check-fit` | decision (choice `standard`/`custom`) | Whether the task asks for more than the default is a judgment over free text with a fixed answer space; it also catches a wrong column map. Threshold 0.7 because building the wrong thing is costly. |
| `by-mode` | router | Standard -> verify; custom -> extend first. |
| `customize-app` | client_task | Extra charts/columns/layouts are open-ended code generation. |
| `verify-app` | execution (`scripts/verify_app.py`, Playwright) | Every requirement is checkable: files, data copy, render over http and file://, console errors, bubble count, labels, legend, overlap, bounds, clustering, centring, side-by-side, headers, market-cap format and value, tooltip on stock/none on ETF, two-way click linking. |
| `by-verdict` | router | Pass -> end; fail -> repair. |
| `repair-app` | client_task | Fixing an arbitrary failure is code editing; the template lists the usual cause per check and requires re-running the verifier. |

Two scripts, not one per concern: build and verify are independent and each also runs as
a CLI (`--data-dir/--output-dir`) for the client tasks' re-runs.

## Where the source content went

| Source item | Where in the compiled skill |
|---|---|
| Description / when to use (charts, axes, legends, tooltips, SVG for web) | frontmatter `description`, `trigger_when` |
| "Quick table or summary -> don't use D3" | `do_not_use_when[0]`, references/d3-patterns.md |
| Inputs to expect (files, chart intent fields, output constraints) | references/d3-patterns.md "Inputs and outputs"; build_app.py profiles the data |
| Missing details -> reasonable defaults documented at the top of the output file | header comment of assets/app/visualization.js; d3-patterns.md |
| Outputs dist/chart.html, chart.svg, optional png; predictable folder unless task specifies | d3-patterns.md (task paths win, as the source says) |
| Data determinism (sort rows, stable group order, explicit formats) | visualization.js `sortRows`/`sectorOrder`/`formatMarketCap`; d3-patterns.md |
| Rendering determinism (no random, no transitions, fixed size/viewBox, force layout fixed starts + N ticks + stop) | visualization.js `layout()` (spiral starts, `.stop()`, 400+60 ticks), fixed 700x620 viewBox; anti_patterns; d3-patterns.md |
| Offline: no CDN, pin version, vendor bundle | build_app.py + assets/vendor; verify "no CDN script tags"; anti_patterns |
| File determinism (stable IDs, LF, numeric precision) | build_app.py writes with `newline="\n"`; fixed ids (`bubble-chart`, `data-table`); `toFixed(2)` on positions; d3-patterns.md |
| Recommended layout dist/ + vendor/ | d3-patterns.md (overridden by the task's required layout) |
| Tooltip pattern (div#tooltip, CSS .visible + opacity, pointer-events none, pageX/Y) | assets/app/index.html, style.css, visualization.js `showTooltip`; d3-patterns.md |
| Click handler for selection (`selected` class, stroke CSS) | visualization.js `selectTicker`, style.css; d3-patterns.md |
| Conditional interactivity (exit early for excluded category) | `showTooltip` returns for `isETF`; verify check; anti_patterns |
| bubble_chart_example.js: scaleSqrt radius, uniform radius for missing value, ordinal color by sector, collide r+2, sector anchors + forceX/forceY, ETF tooltip guard, selectBubble -> highlightTableRow | visualization.js `layout`/`drawBubbles`/`selectTicker` (`window.highlightTableRow`); d3-patterns.md "Bubble chart" |
| interactive_table_example.js: table structure, key function, row click -> select + highlightBubble, formatNumber T/B/M/K, table CSS (selected/highlighted rows) | visualization.js `drawTable`, `formatMarketCap`, `window.highlightBubble`; style.css; d3-patterns.md |
| interactive_table_example.js: click-to-sort columns | d3-patterns.md (optional; not built by default, see drops) |
| tooltip_handler.js: TooltipHandler (shouldShow, formatContent, offsets, move, attach, auto-create element), example usages, formatNumber, required CSS (.tooltip-header/.tooltip-body) | behaviour inlined in visualization.js tooltip functions; pattern summarised in d3-patterns.md |
| check_tooltip.js: element exists, .visible mechanism, opacity, content | scripts/verify_app.py tooltip checks; d3-patterns.md "Verifying tooltips" |

## Deliberate drops (with rationale)

- **Default D3 version d3@7.9.0** — replaced by the task's v6 requirement; the source
  itself says task constraints win. Kept as a note in d3-patterns.md.
- **Exporting chart.svg / chart.png** — not requested by this task type; the source marks
  PNG optional and SVG "optional but nice". Mentioned in d3-patterns.md for other tasks.
- **`forceCenter` + `forceManyBody(-30)` from bubble_chart_example.js** — they work against
  sector clustering and compactness at this size; replaced by size-aware anchors. Recorded in
  d3-patterns.md so the change is visible.
- **Live `simulation.on('tick')` updates** — contradicts the source's own determinism rule;
  replaced by stop + fixed ticks.
- **`d3.csv('/data/stocks.csv')` absolute path** — breaks under file:// and subpaths; the app
  uses the relative `data/<file>` with an embedded fallback.
- **Column sorting in the table** — optional in the source example and not asked by the task;
  sorting re-orders rows and is a risk for checkers that expect the data order. Pattern kept
  in d3-patterns.md for custom tasks.
- **TooltipHandler class, its four usage examples, `.tooltip-header/.tooltip-body` CSS,
  table-tooltip example, and module.exports** — illustrative scaffolding; the behaviour they
  demonstrate (conditional show, formatted content, follow mouse, CSS class visibility) is
  implemented directly.
- **check_tooltip.js console logging and its 1-second auto-hide demo** — manual debugging aid;
  superseded by the automated Playwright checks.
- **`tr.highlighted` (yellow) vs `tr.selected` (blue) as two separate states** — one shared
  `selected` state drives both directions so the bubble and row can never disagree; the
  stylesheet styles `.highlighted` identically for compatibility.
- **"Use LF line endings" / numeric precision as checks** — applied in code; not separately
  verified (no behavioural effect in the browser).
