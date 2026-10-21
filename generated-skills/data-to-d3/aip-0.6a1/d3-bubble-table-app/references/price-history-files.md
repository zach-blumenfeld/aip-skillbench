# Per-ticker price-history CSVs (`data/indiv-stock/` in the reference task)

Load this only when a change reads the price files (e.g. a line chart of a selected ticker).

- One file per row of the descriptions CSV. File stems do **not** share the ticker's case:
  stocks are upper case (`AAPL.csv`), ETFs lower case (`spy.csv`, `qqq.csv`) while the
  descriptions CSV says `SPY`. Match case-insensitively; `build_app.py` reports any
  ticker without a file (`data_profile.tickers_without_price_file`).
- Two column layouts, both with an unnamed leading index column (header starts with `,`):
  - stocks: `,Date,Low,Open,Volume,High,Close,Adjusted Close`
  - ETFs:   `,Date,Open,High,Low,Close,Volume,OpenInt` (no `Adjusted Close`)
  Read columns by name, never by position; use `Close` when a series must exist for every
  ticker, `Adjusted Close` only when present.
- `Date` is ISO `YYYY-MM-DD`; parse with `d3.timeParse('%Y-%m-%d')` and sort ascending.
  In the reference data every file covers 2016-01-04 .. 2017-11-10 (~470 trading days),
  but another instance may differ: derive domains from the data.
- Load with `d3.csv('data/<dir>/<file>')` relative to `index.html`. From `file://` the
  fetch is blocked; either embed the needed series at build time (as the bubble chart's
  fallback does) or note that the page needs an HTTP server for that panel.
