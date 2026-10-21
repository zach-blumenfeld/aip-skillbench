---
name: d3-stock-bubble-table
description: Build an offline single-page D3.js v6 web app from stock CSVs. It draws a force-clustered bubble chart (sized by market cap, colored by sector, with legend, ticker labels and hover tooltips) next to a data table, and clicking a bubble or a row highlights both. Scripts inspect the data, generate index.html, css/style.css, js/visualization.js and a vendored js/d3.v6.min.js, copy the data, then verify the result in headless Chromium. Use for "visualize stock/company data with D3", bubble chart plus linked table, forceX/forceY sector clusters, forceCollide, or tooltip/click-highlight tasks.
compatibility: Python >= 3.8 (standard library) for scripts/build_app.py. scripts/verify_app.py also needs the pip package `playwright` with Chromium installed (`playwright install chromium`). No Node packages and no network needed, because D3 v6.7.0 is vendored in assets/.
---

# D3 Stock Bubble Chart + Linked Table

## Trigger When

- A task asks for a D3.js (v6) web app that visualizes stock or company data, such as `stock-descriptions.csv` plus per-ticker price-history CSVs.
- The task wants a bubble chart sized by market cap, colored or clustered by sector (forceX/forceY, forceCollide), with a legend, labels and tooltips.
- The task wants a data table beside the chart, with formatted market caps (e.g. `1.64T`) and two-way click highlighting between bubble and row.
- More broadly: any offline, deterministic D3 chart with tooltips, click-to-highlight, or a vendored D3 bundle.

Do not use when the user only needs a table or summary. Give them markdown or a spreadsheet instead of D3.

## Purpose

This skill turns a company-descriptions CSV (ticker, name, sector, market cap) and its data folder into a working single-page app: `index.html`, `css/style.css`, `js/visualization.js`, `js/d3.v6.min.js`, plus a copy of the data. It adds tested pieces you would otherwise rebuild by trial and error. These are: column auto-mapping, a rule for spotting ETFs, a deterministic force layout that fits and centers sector clusters with no overlap, a tooltip that ETFs never trigger, linked selection, an embedded data fallback so the page also works from `file://`, and a headless-browser verifier that checks every requirement against the CSV.

## Procedure

Run every command from this skill's folder. Paths below use the task's container layout (`/root/data` in, `/root/output` out). Substitute whatever the task statement says.

- [ ] 1. Prerequisites: run `python3 --version` (need >= 3.8) and `python3 -c "import playwright"`. Name anything missing. If playwright is missing, still build, then verify with `--static-only` and report that browser checks were skipped.
- [ ] 2. Inspect (execution): `python3 scripts/build_app.py inspect --data-dir /root/data`
- [ ] 3. Judge the inspection (decision, below).
- [ ] 4. Build (execution), passing the overrides from step 3:
  `python3 scripts/build_app.py build --data-dir /root/data --out /root/output [--col ROLE=COLUMN ...] [--etf-sector LABEL] [--descriptions FILE] [--title "..."]`
- [ ] 5. Only if `scope` = `extended`: extend the app (client task, below).
- [ ] 6. Verify (execution), with the same `--col` / `--etf-sector` / `--descriptions` flags as the build:
  `python3 scripts/verify_app.py --out /root/output --data-dir /root/data [same flags]`
  Exit 0 means every check passed. On any `FAIL`, fix it, rebuild (or re-edit), and re-verify until it exits 0.
- [ ] 7. Report (client task, below).

### Step 2 output (inspect)

The output is JSON with these fields:
- `descriptions`: the CSV it picked. Default `stock-descriptions.csv`, else the only top-level CSV.
- `columns`, and `mapping`: role -> column for `ticker, name, sector, marketCap, country, website`.
- `sectors` with counts, `etf_tickers`, `stocks_without_market_cap`.
- `sample_market_cap_format`.
- `price_history`: per-ticker price files matched case-insensitively.
- `warnings`.

A row counts as an ETF when its sector equals `--etf-sector` (default `ETF`, case-insensitive), or when it has no market cap, no country and no website.

### Step 3 decision: judge the inspection

Input: the inspect JSON plus the task statement. Answer all three questions in one pass.

```yaml
mapping_correct:
  type: noul
  instructions: Does every role in `mapping` point to the column that really holds it? ticker = symbol, name = full company name (not a short or summary field), sector = sector or category, marketCap = numeric market capitalization.
  criteria:
    true: All four required roles are mapped and each column's meaning matches its role.
    false: A required role is null, or a column is wrong (e.g. name -> a short name when a full-name column exists).
etf_rule_correct:
  type: noul
  instructions: Do `etf_tickers` match exactly the entries the task says must get uniform size and no tooltip (ETFs, funds, rows without market cap)?
  criteria:
    true: The set matches. Or the task excludes no entries and `etf_tickers` is empty.
    false: Funds are labelled with another sector (e.g. "Funds"), or the list holds rows that should keep their tooltip.
scope:
  type: choice
  instructions: How does the task's requested app compare with what build_app.py generates? The generated app is a bubble chart (market cap size, sector color, forceX/forceY clusters, forceCollide, legend, ticker labels, tooltip with ticker/name/sector, none for ETFs) side by side with a table (columns "Ticker symbol", "Full company name", "Sector", "Market cap"), two-way click highlight, and files index.html, css/style.css, js/visualization.js, js/d3.v6.min.js, data/.
  criteria:
    standard: The task asks for that app and nothing the template lacks.
    extended: The task also asks for something the template lacks or words differently, e.g. a price-history line chart, other table columns or headers, other tooltip fields, a different layout or file names.
    other: The task is not this chart family. Use references/d3-patterns.md and write the visualization yourself.
```

Act on the answers:
- `mapping_correct` = false: add `--col ROLE=COLUMN` for each wrong or missing role, rerun inspect with the same flags, and re-answer.
- `etf_rule_correct` = false: pass `--etf-sector <the funds label>` and rerun inspect. If no single label fits, build anyway and adjust `isETF` in `normalize()` during step 5.
- Costly mistakes: a wrong `true` for either noul ships a wrong chart. Reconsider close calls that lean `true`. For `scope`, reconsider any close call that leans `standard`.

### Step 5 client task: extend the generated app (scope = extended)

Edit the generated files in the output folder, not the skill's templates. Read [references/d3-patterns.md](references/d3-patterns.md) first: it covers the determinism rules, the tooltip and click patterns, and the number format. Keep the contracts that `verify_app.py` and the task rely on:
- Circles keep class `bubble`, are bound to row objects with `.ticker`, and carry `data-ticker`. Labels keep `pointer-events: none`.
- Table rows are bound with `.data(rows, d => d.ticker)`. Highlighting uses the classes `selected` / `highlighted`, set from one `select(ticker)` function.
- The `#tooltip` element shows with the `.visible` class and stays hidden for `isETF` rows.
- Keep the D3 v6 handler signature `(event, d)`, with no CDN script and no `Math.random`.

Price histories are under `data/<subfolder>/<ticker>.csv`. ETF file names may be lowercase, so match tickers case-insensitively (inspect lists them). Each has a leading unnamed index column, and the columns differ by file: stocks have `Date,Low,Open,Volume,High,Close,Adjusted Close`, ETFs have `Date,Open,High,Low,Close,Volume,OpenInt`, so read columns by name. When you need a price file, load it with `d3.csv`. If the page must also work from `file://`, embed it the way `EMBEDDED_ROWS` is embedded.

If the task changes the table headers or tooltip fields, the matching verifier checks will fail by design. Confirm the new behavior by hand in the browser, then report which checks no longer apply and why.

### Step 7 client task: report

Report:
- The output path and the files written.
- The mapping and ETF rule you used, and the sectors with their counts.
- Any inspect warnings.
- The verifier summary line (`N checks, 0 failed`), or which checks were skipped and why.

## What the generated app does (defaults)

- Bubble area scales with market cap (`d3.scaleSqrt`). The largest radius is solved so that bubbles cover about 42% of a fixed 760x640 viewBox, and the minimum radius is 14 so tickers stay readable. ETFs and rows without a cap share one radius, 0.3 x the largest.
- Sector colors come from `d3.schemeCategory10` over the sectors sorted alphabetically, extended with `d3.schemeSet3` past 10 sectors. Labels switch to dark text on light fills. An HTML legend sits above the chart.
- Each sector gets an anchor circle sized by its members' area. The anchors are packed with `d3.packSiblings` and centered. The simulation uses `forceX`/`forceY` at strength 0.12 toward each anchor and `forceCollide(r + 1.5)` with 3 iterations. It runs 400 ticks plus 120 collision-only ticks synchronously from deterministic spiral starts. The result is then uniformly scaled to fit and center in the viewBox, which preserves no-overlap.
- The table is listed in file order, and clicking a header sorts it (missing caps sort last). Market cap uses `T/B/M/K` with 2 decimals, and missing values show `-`.
- `visualization.js` tries `d3.csv('data/<descriptions>')` first and falls back to rows embedded at build time.

## Files

- `scripts/build_app.py`: `inspect` and `build` (steps 2 and 4).
- `scripts/verify_app.py`: headless-Chromium checks against the CSV (step 6). It imports helpers from `build_app.py`.
- `assets/templates/index.html`, `assets/templates/style.css`, `assets/templates/visualization.js`: the app templates the build fills in. Edit them only to change the default app for every future run; for one task, edit the output instead (step 5).
- `assets/d3.v6.min.js` (D3 6.7.0) and `assets/D3-LICENSE.txt`: vendored library and its ISC license. The build copies the library and falls back to downloading it only if the file is missing.
- `references/d3-patterns.md`: load it for step 5 or for scope = `other`.
- `source/`: the original skill and the provenance and drop log (`source/README.md`). The agent does not need to load it at runtime.

## Gotchas

- The real descriptions header is `,ticker,sector,full name,marketCap,...`. The first column has an empty name and the full name is `full name` (with a space). Use `d['full name']`, not `d.name`. Auto-mapping handles this.
- ETF rows have empty `marketCap`, `country` and `website`, and `+'' === 0`. Treat empty as missing, never as a zero-size bubble.
- Load data with relative paths (`data/stock-descriptions.csv`). An absolute path like `/data/stocks.csv`, as in the source example, breaks on `file://` and under any subfolder.
- Chromium blocks `d3.csv`/`fetch` on `file://`. Without the embedded fallback, the page is blank when opened by double-click.
- Text labels on top of circles swallow hover and click unless they have `pointer-events: none`.
- D3 v6 handlers receive `(event, d)`. The v5 `d3.event` is gone.
- The source skill pinned d3@7.9.0, but the task demands v6, so ship `js/d3.v6.min.js` (6.7.0). The task's version always wins.
- An animated force layout keeps moving after load, which breaks the overlap and position checks. Tick it synchronously and stop it.
- Copy `data/` verbatim, keeping the original file names (lowercase ETF price files included).
