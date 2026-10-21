---
name: d3-bubble-table-app
description: Build a single-page D3.js v6 web app from a stock descriptions CSV (ticker, company name, sector, market cap) plus per-ticker price-history CSVs - a sector-clustered force-layout bubble chart (bubble area by market cap, ETFs uniform, forceX/forceY clusters, forceCollide, ticker labels, sector legend, tooltips except for ETFs) side by side with a linked data table (Ticker symbol, Full company name, Sector, Market cap as 1.64T), with two-way click highlighting, vendored offline D3, a copied data/ folder, and headless-browser verification. Use for "visualize stock/company data with D3", bubble chart + table dashboards, index.html + js/visualization.js + css/style.css deliverables.
metadata:
  aip-version: "0.6a1"
  version: "1.0"
---

# AIP runtime — format 0.6a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the one JSON object a run carries. Each step declares the keys it reads as `inputs`; `execution` and `client_task` steps declare the keys they add as `outputs`, and a `decision` adds one key per question.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the procedure's result.

## Execution

The state starts as the start step's `inputs` and flows along `inputs_to`; each step adds its outputs to it. Every key is produced by exactly one step, so keys accumulate and nothing is overwritten. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. A step sees only those keys: give it its declared `inputs` and nothing else from the state. You have the final say at every step.

- **`execution`**: before the first one, check that this machine has everything `requires` names (the interpreter at its minimum version, the packages, the tools); if anything is missing, stop and name all of it. Run `script` from its folder, launched with the step's `command` when it has one and `python <script>` otherwise, with one JSON object on stdin, `{"state": <the step's inputs>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout holding exactly the step's `outputs`; add them to the state. A non-zero exit, or output missing a declared key, fails the step: stop there and report it rather than doing the step by hand.
- **`decision`**: answer each question from the step's inputs, and from the run so far only when the step sets `history: true`. Each answer collapses to one value under its question name and is added to the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the step's inputs, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the step's `outputs`; add them to the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. Those keys are the procedure's result.

```yaml
purpose: >
  Turn a folder of stock data (one descriptions CSV with ticker, company name, sector and
  market cap, plus a sub-folder of per-ticker price-history CSVs) into an offline
  single-page D3.js v6 web app: a deterministic sector-clustered bubble chart beside a
  linked data table. A script profiles the data, maps the columns, vendors D3 v6, copies
  the data and writes index.html, css/style.css, js/visualization.js; a decision checks
  whether the task asks for anything beyond that default; a headless-Chromium script
  verifies every requirement (overlap, clustering, centring, tooltips, linking, layout,
  formats) and failures route to a repair task.

trigger_when:
  - A task asks to visualize stock or company data (descriptions CSV + individual stock price CSVs) with D3.js as a web page.
  - The deliverable is index.html with js/d3.v6.min.js, js/visualization.js, css/style.css and a data/ copy.
  - A bubble chart sized by market cap and clustered by sector must sit next to a table of the same rows, linked by click highlighting.
  - Any D3 chart + table dashboard over a CSV of entities with a category column and a size measure.

do_not_use_when:
  - The user only needs a quick table or summary; use a spreadsheet or markdown, not D3.
  - The visualization must be produced with a non-D3 library (matplotlib, plotly, Recharts) or as a raster image only.
  - There is no tabular entity data with a category column (e.g. a pure time-series line chart task); build that directly with references/d3-patterns.md as guidance.

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - playwright

steps:
  - name: build-app
    kind: execution
    description: Profile the data folder, map columns, vendor D3 v6, copy data/ and write index.html, css/style.css, js/visualization.js.
    inputs:
      - name: data_dir
        type: string
        description: Absolute path of the task's input data folder (e.g. /root/data) holding the descriptions CSV and the price-history sub-folder.
      - name: output_dir
        type: string
        description: Absolute path where the web app goes (e.g. /root/output); created if missing.
      - name: instruction
        type: string
        description: The task statement verbatim; read by the fit check and any client task.
    script: scripts/build_app.py
    assets:
      - assets/app/index.html
      - assets/app/style.css
      - assets/app/visualization.js
    timeout: 120
    outputs:
      - name: data_profile
        type: object
        description: Descriptions file, column map, row count, sector counts, no-market-cap tickers, price-file matching, warnings.
      - name: build_report
        type: object
        description: Files written, data files copied, D3 source, bubble/table row counts, sectors, uniform-size tickers.
    inputs_to: check-fit

  - name: check-fit
    kind: decision
    description: Decide whether the default build already covers the task or the task asks for more.
    inputs:
      - name: instruction
        type: string
      - name: data_profile
        type: object
      - name: build_report
        type: object
    questions:
      build_mode:
        type: choice
        instructions: >
          The default build delivers exactly this: index.html + css/style.css + js/d3.v6.min.js
          (vendored v6) + js/visualization.js + a verbatim data/ copy; a bubble chart with one
          bubble per descriptions row, area by market cap, uniform size for ETFs / rows without
          market cap, sector colors with a legend, forceX/forceY sector clusters centred in the
          chart, forceCollide (no overlap), ticker label inside each bubble, hover tooltip with
          ticker, name and sector (none for ETFs); beside it a table of every row with columns
          Ticker symbol, Full company name, Sector, Market cap (formatted 1.64T / 193.22B); click
          a bubble or a row to highlight both. Compare the task statement against that list.
          Wording differences, restating these features, or naming the same paths are standard.
          Also answer custom when the data profile shows the column map picked the wrong column
          for a field the task names.
        criteria:
          standard: Every requirement in the task is in the default list above; nothing extra is asked.
          custom: The task asks for something the default lacks - an extra chart (e.g. price-history lines from the per-ticker CSVs), other table columns, other encodings or formats, a different layout or file layout - or the column map is wrong.
    thresholds:
      build_mode: 0.7
    inputs_to: by-mode

  - name: by-mode
    kind: router
    description: Standard tasks go straight to verification; custom ones are extended first.
    branch_on: build_mode
    branches:
      standard: verify-app
      custom: customize-app

  - name: customize-app
    kind: client_task
    description: Edit the generated app in place to add what the task asks beyond the default, keeping every default behaviour.
    inputs:
      - name: instruction
        type: string
      - name: output_dir
        type: string
      - name: data_profile
        type: object
      - name: build_report
        type: object
    template: assets/customize.md
    references:
      - path: references/app-structure.md
        description: Map of the generated files - visualization.js functions, CONFIG, CSS classes, data attributes, how to add a panel. Load before editing visualization.js.
      - path: references/d3-patterns.md
        description: D3 determinism rules, tooltip, click-linking, force-cluster and number-format patterns from the source skill. Load when writing new chart code.
      - path: references/price-history-files.md
        description: Layout and gotchas of the per-ticker price CSVs (case of file names, two column schemas, dates). Load only if a change reads them.
    outputs:
      - name: customizations
        type: list[*]
        description: One short string per change - the requirement it serves and the files edited.
    inputs_to: verify-app

  - name: verify-app
    kind: execution
    description: Check files and data copy, then load the page in headless Chromium (http and file://) and test every chart, table, tooltip and linking requirement.
    inputs:
      - name: data_dir
        type: string
      - name: output_dir
        type: string
    script: scripts/verify_app.py
    timeout: 180
    outputs:
      - name: verify_passed
        type: boolean
        description: True only when every check passed.
      - name: verify_report
        type: object
        description: browser_checked, n_checks, n_failed, failures and the full list of checks with observed details.
    inputs_to: by-verdict

  - name: by-verdict
    kind: router
    description: A passing app is done; a failing one goes to repair.
    branch_on: verify_passed
    branches:
      "true": end
      "false": repair-app

  - name: repair-app
    kind: client_task
    description: Fix the causes of the failed checks and re-run the verifier until it passes.
    inputs:
      - name: verify_report
        type: object
      - name: output_dir
        type: string
      - name: data_dir
        type: string
      - name: instruction
        type: string
    template: assets/repair.md
    references:
      - path: references/app-structure.md
        description: Where each behaviour lives in the generated files. Load to locate the cause of a failed check.
      - path: references/d3-patterns.md
        description: Canonical tooltip, linking, force-layout and determinism patterns. Load when rewriting chart code.
    outputs:
      - name: repair_summary
        type: string
        description: What was wrong and what was changed.
      - name: recheck_passed
        type: boolean
        description: True when the final re-run of scripts/verify_app.py passed, or every check still failing is overridden by an explicit task requirement.
    inputs_to: end

  - name: end
    kind: end
    description: The web app in output_dir, with the build summary and the verification report.
    inputs:
      - name: output_dir
        type: string
      - name: build_report
        type: object
      - name: verify_report
        type: object

anti_patterns:
  - Loading D3 from a CDN or using v7 when the task says v6; the container may be offline and the checker looks for js/d3.v6.min.js. build_app.py copies the vendored v6.7.0 bundle.
  - Only fetching the CSV with d3.csv; browsers block fetch from file://, so a double-clicked index.html renders nothing. Keep the embedded-rows fallback.
  - Sizing bubbles by radius instead of area (use scaleSqrt), or giving ETFs a market-cap-derived size; rows without market cap get one uniform radius.
  - Showing a tooltip (or "N/A" fields) for ETFs; they have no marketCap, country or website, so their bubbles get no tooltip at all.
  - Using d3.format('.3s') for market cap; it prints G for billions. Format as 1.64T / 193.22B.
  - Letting the force simulation animate with random jiggle, or adding forceCenter/forceManyBody that pull clusters apart; stop it and tick a fixed count from deterministic starts.
  - Clusters placed on a fixed-radius ring regardless of size; one huge sector (mega-cap tech) then swallows its neighbours, and many sectors leave a hollow centre. Pack per-sector anchor circles sized from their bubbles' area (d3.packSiblings).
  - Matching price files by exact ticker case; ETF files are lower case (spy.csv) while the descriptions say SPY.
  - Reading the leading unnamed index column of the CSVs as data, or reading price columns by position; stock and ETF files have different column orders.
  - Letting the dashboard wrap so the table drops below the chart; the two must stay side by side horizontally.
  - Hardcoding tickers, sectors, counts or the expected market caps; everything comes from the descriptions CSV of the instance at hand.
  - Declaring success without running scripts/verify_app.py; overlap, clustering and linking bugs only show in a real browser.
```
